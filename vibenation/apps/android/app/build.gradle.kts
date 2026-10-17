import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing lives OUTSIDE the repo: /root/vn-secrets/android-release.env
// (VN_KEYSTORE, VN_KEYSTORE_PASSWORD, VN_KEY_ALIAS, VN_KEY_PASSWORD). Override the path with VN_SIGNING_ENV.
val signingEnv = Properties().apply {
    val f = file(System.getenv("VN_SIGNING_ENV") ?: "/root/vn-secrets/android-release.env")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "com.vibenation.camera"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.vibenation.camera"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        // Phones only: keeps the APK small (WebRTC ships a native library per ABI).
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    signingConfigs {
        if (signingEnv.getProperty("VN_KEYSTORE") != null) {
            create("release") {
                storeFile = file(signingEnv.getProperty("VN_KEYSTORE"))
                storePassword = signingEnv.getProperty("VN_KEYSTORE_PASSWORD")
                keyAlias = signingEnv.getProperty("VN_KEY_ALIAS")
                keyPassword = signingEnv.getProperty("VN_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module", "META-INF/DEPENDENCIES")
    }
}

dependencies {
    implementation("io.livekit:livekit-android:2.29.0")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("junit:junit:4.13.2")
}
