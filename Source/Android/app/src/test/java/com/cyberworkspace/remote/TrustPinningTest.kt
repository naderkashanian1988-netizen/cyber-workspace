package com.cyberworkspace.remote.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.PublicKey
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.Date
import javax.security.auth.x500.X500Principal

class TrustPinningTest {

    @Test
    fun `sha256 hex matches the reference vector`() {
        // sha256("abc") per FIPS 180-4
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            TrustPinning.sha256Hex("abc".toByteArray()))
    }

    @Test
    fun `sha256 hex is 64 lowercase chars`() {
        val hex = TrustPinning.sha256Hex("cyber".toByteArray())
        assertEquals(64, hex.length)
        assertEquals(hex, hex.lowercase())
    }

    @Test
    fun `normalize strips separators and case`() {
        assertEquals("abcdef", TrustPinning.normalizeFingerprint("AB:CD: EF\nef"))
    }

    @Test
    fun `format and normalize round trip`() {
        val raw = "0123456789abcdef".repeat(4) // 64 hex chars
        val display = TrustPinning.formatFingerprint(raw)
        assertTrue(display.startsWith("01:23:45"))
        assertEquals(raw, TrustPinning.normalizeFingerprint(display))
    }

    @Test
    fun `leaf fingerprint matches pinned value in any presentation`() {
        val cert = stubCert(derBytes())
        val fp = TrustPinning.fingerprintHex(cert)
        assertEquals(64, fp.length)
        assertTrue(TrustPinning.fingerprintMatches(cert, fp))
        assertTrue(TrustPinning.fingerprintMatches(cert, fp.chunked(2).joinToString(":")))
        assertTrue(TrustPinning.fingerprintMatches(cert, fp.uppercase()))
        assertFalse(TrustPinning.fingerprintMatches(cert, "0".repeat(64)))
        assertFalse(TrustPinning.fingerprintMatches(cert, ""))
    }

    @Test
    fun `pinned trust manager fails closed on mismatch and accepts on match`() {
        val cert = stubCert(derBytes())
        val good = TrustPinning.fingerprintHex(cert)
        // Matching pin accepts (self-signed cannot validate via system CAs,
        // so the pin is exactly what accepts it).
        PinnedTrustManager(good).checkServerTrusted(arrayOf(cert), "RSA")
        // Mismatched pin must throw — fail closed.
        try {
            PinnedTrustManager("f".repeat(64)).checkServerTrusted(arrayOf(cert), "RSA")
            assertFalse("mismatched pin must throw", true)
        } catch (_: CertificateException) {
            // expected
        }
    }

    @Test
    fun `capture trust manager records the leaf fingerprint`() {
        val cert = stubCert(derBytes())
        val capture = CaptureFingerprintTrustManager()
        capture.checkServerTrusted(arrayOf(cert), "RSA")
        assertEquals(TrustPinning.fingerprintHex(cert), capture.capturedLeafFingerprint)
    }

    // ---- minimal X509Certificate stub (no BouncyCastle needed) -------------
    private fun derBytes(): ByteArray =
        // Arbitrary DER-ish bytes; only the digest over encoded form matters.
        ByteArray(256) { i -> (i * 7 + 3).toByte() }

    private fun stubCert(encoded: ByteArray): X509Certificate =
        object : X509Certificate() {
            override fun getEncoded(): ByteArray = encoded.copyOf()
            override fun checkValidity() {} // stub: always valid
            override fun getNotBefore(): Date = Date(0)
            override fun getNotAfter(): Date = Date(Long.MAX_VALUE / 2)
            override fun getVersion(): Int = 3
            override fun getSerialNumber(): java.math.BigInteger = java.math.BigInteger.ONE
            override fun getIssuerDN(): java.security.Principal = X500Principal("CN=CYBER WORKSPACE")
            override fun getSubjectDN(): java.security.Principal = X500Principal("CN=CYBER WORKSPACE")
            override fun getSigAlgName(): String = "SHA256withRSA"
            override fun getSigAlgOID(): String = "1.2.840.113549.1.1.11"
            override fun getSigAlgParams(): ByteArray? = null
            override fun getSignature(): ByteArray = ByteArray(8)
            override fun getIssuerX500Principal(): X500Principal = X500Principal("CN=CYBER WORKSPACE")
            override fun getSubjectX500Principal(): X500Principal = X500Principal("CN=CYBER WORKSPACE")
            override fun getTBSCertificate(): ByteArray = ByteArray(16)
            override fun getTBSCertificate(sigAlg: ByteArray): ByteArray = ByteArray(16)
            override fun getPublicKey(): PublicKey = object : PublicKey {
                override fun getAlgorithm() = "RSA"
                override fun getFormat() = "X.509"
                override fun getEncoded(): ByteArray = ByteArray(4)
            }
            override fun verify(key: PublicKey) {}
            override fun verify(key: PublicKey, sigProvider: String?) {}
            override fun toString(): String = "StubCert"
            override fun getFormat() = "X.509"
            override fun getAlgorithm() = "RSA"
        }  // object : X509Certificate — expression body of stubCert ends here
}  // TrustPinningTest
