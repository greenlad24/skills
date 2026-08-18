import java.io.File
import java.time.LocalDateTime

plugins {
    id("com.android.application")
    kotlin("android")
    id("org.jetbrains.kotlin.plugin.compose")
}

/**
 * Which commit is in this APK. The show log prints it, because reading
 * a night's log means knowing which version's behaviour is on the page
 * — and the behaviour changes between gigs.
 *
 * Read off the environment (CI sets it) or straight out of .git, never
 * by shelling out: a build that fails because `git` is missing would be
 * a silly way to lose a gig.
 */
fun gitSha(): String {
    System.getenv("GITHUB_SHA")?.takeIf { it.isNotBlank() }
        ?.let { return it.take(7) }
    return try {
        val gitDir = rootProject.file("../.git")
        val head = File(gitDir, "HEAD").readText().trim()
        if (!head.startsWith("ref:")) head.take(7) else {
            val ref = head.removePrefix("ref:").trim()
            val f = File(gitDir, ref)
            if (f.exists()) f.readText().trim().take(7)
            else File(gitDir, "packed-refs").readLines()
                .firstOrNull { it.endsWith(" $ref") }
                ?.take(7) ?: "unknown"
        }
    } catch (e: Exception) { "unknown" }
}

/**
 * A versionCode that CHANGES every build. This one number is what
 * Android uses to decide an install is newer than the one already on
 * the tablet — a static versionCode means "install over" can silently
 * keep the OLD apk, which is exactly the trap that had the operator
 * staring at a build that was two fixes behind. CI passes its run number
 * (monotonic, always up); a local build falls back to the git commit
 * count, and finally to 1. Whatever the source, it moves forward.
 */
fun dynamicVersionCode(): Int {
    System.getenv("GITHUB_RUN_NUMBER")?.trim()?.toIntOrNull()
        ?.takeIf { it > 0 }?.let { return 1000 + it }
    return try {
        val gitDir = rootProject.file("../.git")
        // commit count off the packed + loose logs is enough to move
        val n = File(gitDir, "logs/HEAD").takeIf { it.exists() }
            ?.readLines()?.size ?: 0
        if (n > 0) n else 1
    } catch (e: Exception) { 1 }
}

android {
    namespace = "com.stagemix.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.stagemix.app"
        minSdk = 29
        targetSdk = 35
        versionCode = dynamicVersionCode()
        versionName = "0.1.${dynamicVersionCode()} · ${gitSha()}"
        buildConfigField("String", "GIT_SHA", "\"${gitSha()}\"")
        buildConfigField("String", "BUILT_AT",
            "\"${LocalDateTime.now()}\"")
    }

    signingConfigs {
        create("release") {
            // Consistent-key signing so updates install over each other.
            // Default: the checked-in convenience keystore (fine for
            // sideloading to your own tablets — see README to rotate to
            // a private keystore via env/secrets).
            val ks = rootProject.file(
                System.getenv("STAGEMIX_KEYSTORE") ?: "keystore/stagemix.keystore")
            if (ks.exists()) {
                storeFile = ks
                storePassword = System.getenv("STAGEMIX_KS_PASS") ?: "stagemix"
                keyAlias = System.getenv("STAGEMIX_KEY_ALIAS") ?: "stagemix"
                keyPassword = System.getenv("STAGEMIX_KEY_PASS") ?: "stagemix"
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            val cfg = signingConfigs.getByName("release")
            if (cfg.storeFile?.exists() == true) signingConfig = cfg
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(project(":engine"))
    implementation(platform("androidx.compose:compose-bom:2024.09.03"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.2")
    // FileProvider, for sharing the show log out to WhatsApp / mail
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
