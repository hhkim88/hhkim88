plugins {
    id("org.jetbrains.kotlin.jvm") version "1.9.24"
}

dependencies {
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
}

kotlin {
    jvmToolchain(21)
}
