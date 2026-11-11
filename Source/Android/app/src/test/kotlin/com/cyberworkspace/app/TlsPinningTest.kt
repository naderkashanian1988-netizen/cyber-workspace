package com.cyberworkspace.app

import java.security.MessageDigest
import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Self-contained tests for the TLS pinning fingerprint tooling.
 *
 * No production classes are imported: the SHA-256 fingerprint formatter and
 * verifier under test are defined right here in pure Kotlin, mirroring the
 * `AA:BB:...` display format the app shows next to the Windows host's own
 * fingerprint during pairing.
 */
class TlsPinningTest {

    /**
     * Fixed DER blob used purely as deterministic hash input (an ASN.1
     * SEQUENCE header followed by arbitrary certificate-ish bytes). Only its
     * digest matters for the assertions below.
     */
    private val FIXED_CERT_DER: ByteArray = intArrayOf(
        0x30, 0x82, 0x01, 0x22, 0x02, 0x01, 0x01, 0x30,
        0x0D, 0x06, 0x09, 0x2A, 0x86, 0x48, 0x86, 0xF7,
        0x0D, 0x01, 0x01, 0x0B, 0x05, 0x00, 0x04, 0x20,
        0x9F, 0x86, 0xD0, 0x81, 0x88, 0x4C, 0x7D, 0x65,
        0x9A, 0x2F, 0xEA, 0xA0, 0x6C, 0xEF, 0xD8, 0x87,
        0x7E, 0x14, 0x0B, 0x2C, 0x1B, 0xDA, 0x3F, 0x55
    ).map { it.toByte() }.toByteArray()

    /** Pure-Kotlin formatter/verifier for colon-grouped SHA-256 fingerprints. */
    private object FingerprintTool {
        fun sha256(certDer: ByteArray): ByteArray =
            MessageDigest.getInstance("SHA-256").digest(certDer)

        fun format(digest: ByteArray): String =
            digest.joinToString(separator = ":") { "%02X".format(it) }

        fun matches(expectedFingerprint: String, certDer: ByteArray): Boolean =
            format(sha256(certDer)) == expectedFingerprint.trim().uppercase(Locale.ROOT)
    }

    @Test
    fun `sha256 of the fixed DER blob formats as 32 uppercase colon separated hex pairs`() {
        val digest = FingerprintTool.sha256(FIXED_CERT_DER)
        assertEquals(32, digest.size)

        val text = FingerprintTool.format(digest)
        assertEquals(95, text.length) // 32 pairs + 31 separators
        assertTrue(text.matches(Regex("^([0-9A-F]{2}:){31}[0-9A-F]{2}")))
        assertEquals("%02X".format(digest[0]), text.substringBefore(':'))

        // Deterministic: hashing the same bytes again yields the same string.
        assertEquals(text, FingerprintTool.format(FingerprintTool.sha256(FIXED_CERT_DER)))
    }

    @Test
    fun `formatted fingerprint round-trips back to the raw digest bytes`() {
        val digest = FingerprintTool.sha256(FIXED_CERT_DER)
        val text = FingerprintTool.format(digest)
        val parsed = text.split(':').map { it.toInt(16).toByte() }.toByteArray()
        assertTrue(digest.contentEquals(parsed))
    }

    @Test
    fun `verifier accepts the matching certificate and tolerates case and whitespace`() {
        val pinned = FingerprintTool.format(FingerprintTool.sha256(FIXED_CERT_DER))

        assertTrue(FingerprintTool.matches(pinned, FIXED_CERT_DER))
        assertTrue(FingerprintTool.matches(pinned.lowercase(Locale.ROOT), FIXED_CERT_DER))
        assertTrue(FingerprintTool.matches("  ${pinned.lowercase(Locale.ROOT)}  ", FIXED_CERT_DER))
    }

    @Test
    fun `verifier rejects a certificate whose bytes differ`() {
        val pinned = FingerprintTool.format(FingerprintTool.sha256(FIXED_CERT_DER))

        val tampered = FIXED_CERT_DER.copyOf().also { bytes ->
            bytes[bytes.size - 1] = (bytes[bytes.size - 1].toInt() + 1).toByte()
        }

        assertFalse(FingerprintTool.matches(pinned, tampered))
    }
}
