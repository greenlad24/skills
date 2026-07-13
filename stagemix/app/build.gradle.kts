plugins {
    id("com.android.application")
    kotlin("android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.stagemix.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.stagemix.app"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
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
    }
}

dependencies {
    implementation(project(":engine"))
    implementation(platform("androidx.compose:compose-bom:2024.09.03"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
