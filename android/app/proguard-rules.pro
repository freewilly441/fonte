# TensorFlow Lite
-keep class org.tensorflow.** { *; }
-keep class org.tensorflow.lite.** { *; }

# Android Lifecycle
-keep class androidx.lifecycle.** { *; }

# Room Database
-keep class androidx.room.** { *; }

# Keep all custom application classes
-keep class com.fonte.** { *; }

# Generic Signature
-keepattributes Signature
-keepattributes EnclosingMethod

# Suppress warnings
-dontwarn org.tensorflow.**
-dontwarn androidx.**
