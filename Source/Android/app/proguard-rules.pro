# CYBER WORKSPACE Android — release rules.

-keepattributes Signature, InnerClasses, EnclosingMethod, *Annotation*

# --- kotlinx.serialization models of the protocol layer ---
# (com.cyberworkspace.app.protocol mirrors Source/Windows/cyber_workspace/protocol/messages.py)
-keep,includedescriptorclasses class com.cyberworkspace.app.protocol.**$$serializer { *; }
-keepclassmembers class com.cyberworkspace.app.protocol.** {
    *** Companion;
}
-keepclasseswithmembers class com.cyberworkspace.app.protocol.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# --- OkHttp / Okio platform probes ---
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
