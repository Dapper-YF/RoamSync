import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.util.Properties

val localEnvironment = Properties().apply {
    val environmentFile = rootProject.file("../.env")
    if (environmentFile.exists()) environmentFile.reader(Charsets.UTF_8).use { load(it) }
}
fun publicMapValue(name: String): String = "\"" + (System.getenv(name) ?: localEnvironment.getProperty(name, "")).trim().trim('"', '\'').replace("\\", "\\\\").replace("\"", "\\\"") + "\""

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.kotlin.kapt)
    alias(libs.plugins.hilt)
}

android {
    namespace = "com.roamsync.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.roamsync.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "0.2.0"
        buildConfigField("String", "AMAP_WEB_KEY", publicMapValue("AMAP_WEB_KEY"))
        buildConfigField("String", "AMAP_ANDROID_KEY", publicMapValue("AMAP_ANDROID_KEY"))
        manifestPlaceholders["AMAP_ANDROID_KEY"] = (System.getenv("AMAP_ANDROID_KEY") ?: localEnvironment.getProperty("AMAP_ANDROID_KEY", "")).trim().trim('"', '\'')
        buildConfigField("String", "AMAP_SECURITY_CODE", publicMapValue("AMAP_SECURITY_CODE"))

        testInstrumentationRunner = "com.roamsync.app.smoke.NativeSmokeInstrumentation"
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".v2preview"
            val apiBaseUrl = (System.getenv("ANDROID_API_BASE_URL")
                ?: localEnvironment.getProperty("ANDROID_API_BASE_URL", "http://127.0.0.1:3000/"))
                .trim().trim('"', '\'').trimEnd('/') + "/"
            require(apiBaseUrl.startsWith("http://") || apiBaseUrl.startsWith("https://")) {
                "ANDROID_API_BASE_URL must be an HTTP(S) URL"
            }
            buildConfigField("String", "API_BASE_URL", "\"${apiBaseUrl.replace("\\", "\\\\").replace("\"", "\\\"")}\"")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("String", "API_BASE_URL", "\"https://api.roamsync.example/\"")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

kapt {
    correctErrorTypes = true
}

dependencies {
    val composeBom = platform(libs.androidx.compose.bom)
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.hilt.android)
    kapt(libs.hilt.compiler)
    implementation(libs.retrofit.core)
    implementation(libs.retrofit.serialization)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.datastore.preferences)
    // Official AMap Navigation SDK V11.2.100 combined package.  It bundles
    // navigation, 3D map, location and search; keep this exact release pinned.
    implementation("com.amap.api:navi-3dmap-location-search:11.2.100_3dmap11.2.100_loc11.2.100_sea9.8.1")

    debugImplementation(libs.androidx.compose.ui.tooling)
    testImplementation(libs.junit)
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
}
