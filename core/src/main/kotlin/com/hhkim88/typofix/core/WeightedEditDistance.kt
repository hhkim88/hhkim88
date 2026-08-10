package com.hhkim88.typofix.core

/** Levenshtein distance where substitution cost comes from [KeyboardAdjacency] instead of a flat 1. */
object WeightedEditDistance {

    fun compute(a: List<Char>, b: List<Char>): Double {
        val n = a.size
        val m = b.size
        val dp = Array(n + 1) { DoubleArray(m + 1) }
        for (i in 0..n) dp[i][0] = i.toDouble()
        for (j in 0..m) dp[0][j] = j.toDouble()

        for (i in 1..n) {
            for (j in 1..m) {
                val substitutionCost = KeyboardAdjacency.substitutionCost(a[i - 1], b[j - 1])
                dp[i][j] = minOf(
                    dp[i - 1][j] + 1.0,
                    dp[i][j - 1] + 1.0,
                    dp[i - 1][j - 1] + substitutionCost
                )
            }
        }
        return dp[n][m]
    }
}
