plugins {
    kotlin("jvm")
    application
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(project(":engine"))
    implementation(project(":replay"))
    // MP3 decoding through the standard javax.sound SPI, so an mp3 opens
    // exactly like a wav. Pure Java — nothing native to install.
    implementation("com.googlecode.soundlibs:mp3spi:1.9.5.4")
    testImplementation(kotlin("test"))
}

application { mainClass.set("com.stagemix.vm18.MainKt") }

tasks.test { useJUnitPlatform() }

val fatJar by tasks.registering(Jar::class) {
    archiveFileName.set("virtual-m18.jar")
    manifest { attributes("Main-Class" to "com.stagemix.vm18.MainKt") }
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    from(sourceSets.main.get().output)
    dependsOn(configurations.runtimeClasspath)
    from({
        configurations.runtimeClasspath.get()
            .filter { it.name.endsWith("jar") }.map { zipTree(it) }
    }) { exclude("META-INF/*.SF", "META-INF/*.DSA", "META-INF/*.RSA") }
}
