package com.cyberworkspace.app.net

import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Trust-on-first-use replacement for the default CA trust: the ONLY thing that
 * makes a server certificate acceptable is a SHA-256 fingerprint equal to the
 * one stored on this device during pairing (PROTOCOL.md §1, §4). The check is
 * done against the leaf certificate of the presented chain.
 *
 * Stored fingerprint format: hex, uppercase, colon-grouped — "AA:BB:…". Any
 * mismatch aborts the handshake with a CertificateException.
 */
class FingerprintPinningTrustManager(storedFingerprint: String) : X509TrustManager {

    private val expected: String = normalizeFingerprint(storedFingerprint)

    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
        // The client never presents a certificate; this path must not happen.
        throw CertificateException("client certificates are not used by CyberWorkspace")
    }

    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
        if (chain.isEmpty()) {
            throw CertificateException("server sent an empty certificate chain")
        }
        val leaf = chain[0]
        val actual = FingerprintCalc.fingerprintOf(leaf)
        if (!actual.equals(expected, ignoreCase = true)) {
            throw CertificateException(
                "certificate fingerprint mismatch: expected=$expected actual=$actual"
            )
        }
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()

    companion object {
        /** Strips colons/whitespace and uppercases, so "aa:bb" and "AABB" compare equal. */
        fun normalizeFingerprint(raw: String): String =
            raw.replace(":", "").replace(" ", "").trim().uppercase()
    }
}

/** SHA-256 certificate fingerprint calculator (SPKI/cert pinning, PROTOCOL.md §1). */
object FingerprintCalc {

    /** Returns e.g. "3A:F2:0B:…": 64 hex chars, uppercase, grouped by ":". */
    fun fingerprintOf(cert: X509Certificate): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(cert.encoded)
        return digest.joinToString(separator = ":") { byte -> String.format("%02X", byte) }
    }
}

/**
 * Builds a pinned (SSLSocketFactory, X509TrustManager) pair. Wire it into
 * OkHttpClient via `client.sslSocketFactory(factory, trustManager)`; the trust
 * manager must be kept because OkHttp requires both parts of the pair.
 */
fun sslSocketFactory(fingerprint: String): Pair<SSLSocketFactory, X509TrustManager> {
    val trustManager = FingerprintPinningTrustManager(fingerprint)
    val context = SSLContext.getInstance("TLS")
    context.init(null, arrayOf<TrustManager>(trustManager), SecureRandom())
    return context.socketFactory to trustManager
}

/**
 * Hostname verifier for pinned connections. Identity is established by the
 * certificate fingerprint (the host presents a self-signed certificate whose
 * CN/SAN need not match its address), so default hostname verification is
 * replaced by the pinning check that already ran in checkServerTrusted.
 */
fun fingerprintHostnameVerifier(): HostnameVerifier = HostnameVerifier { _, _ -> true }
