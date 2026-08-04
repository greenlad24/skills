pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    plugins {
        id("com.android.application") version "8.7.3"
        kotlin("jvm") version "2.0.21"
        kotlin("android") version "2.0.21"
        id("org.jetbrains.kotlin.plugin.compose") version "2.0.21"
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "stagemix"

include(":engine")

// Offline replay of a recorded multitrack through the real engine.
// Pure JVM, no Android SDK needed.
include(":replay")

// The :app module needs the Android SDK. Skip it when no SDK is present
// so `gradle :engine:test` runs on any dev box (engine is pure JVM).
val hasSdk = System.getenv("ANDROID_HOME") != null ||
    System.getenv("ANDROID_SDK_ROOT") != null ||
    File(rootDir, "local.properties").let { it.exists() && "sdk.dir" in it.readText() }
if (hasSdk) include(":app")
