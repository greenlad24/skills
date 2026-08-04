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
    testImplementation(kotlin("test"))
}

application {
    mainClass.set("com.stagemix.replay.MainKt")
}

tasks.test { useJUnitPlatform() }

/**
 * One self-contained jar, so a night can be replayed on the machine
 * that holds the recording without installing anything but Java:
 *     java -jar stagemix-replay.jar /path/to/session
 */
val fatJar by tasks.registering(Jar::class) {
    archiveFileName.set("stagemix-replay.jar")
    manifest { attributes("Main-Class" to "com.stagemix.replay.MainKt") }
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    from(sourceSets.main.get().output)
    dependsOn(configurations.runtimeClasspath)
    from({
        configurations.runtimeClasspath.get()
            .filter { it.name.endsWith("jar") }.map { zipTree(it) }
    }) { exclude("META-INF/*.SF", "META-INF/*.DSA", "META-INF/*.RSA") }
}
