package com.hhkim88.typofix.core

import kotlin.math.sqrt

/**
 * Approximate physical position of each 두벌식 (unshifted) letter key, based on standard QWERTY
 * stagger. This exists purely to estimate how "close" a typo substitution is: swapping a jamo for
 * one on a neighboring key (a joint/finger-slip typo) should cost less in an edit distance than
 * swapping it for something on the far side of the keyboard.
 */
object KeyboardAdjacency {

    private val positions: Map<Char, Pair<Double, Double>> = buildMap {
        val row1 = listOf('ㅂ', 'ㅈ', 'ㄷ', 'ㄱ', 'ㅅ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅐ', 'ㅔ')
        row1.forEachIndexed { i, jamo -> put(jamo, i.toDouble() to 0.0) }

        val row2 = listOf('ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ')
        row2.forEachIndexed { i, jamo -> put(jamo, (i + 0.5) to 1.0) }

        val row3 = listOf('ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ')
        row3.forEachIndexed { i, jamo -> put(jamo, (i + 0.75) to 2.0) }
    }

    /**
     * 0.0 for the same key, rising toward 1.0 ("no better than any other substitution") the
     * farther apart two keys are. Characters we have no position for (non-letter jamo, digits,
     * punctuation, or anything not on this layout) always cost the full 1.0.
     */
    fun substitutionCost(a: Char, b: Char): Double {
        if (a == b) return 0.0
        val pa = positions[a] ?: return 1.0
        val pb = positions[b] ?: return 1.0
        val dx = pa.first - pb.first
        val dy = pa.second - pb.second
        val distance = sqrt(dx * dx + dy * dy)
        return (0.25 + 0.4 * distance).coerceAtMost(1.0)
    }
}
