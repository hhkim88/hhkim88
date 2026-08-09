package com.hhkim88.typofix.ime

interface KeyboardActionListener {
    fun onHangulJamo(jamo: Char)
    fun onSymbol(char: Char)
    fun onBackspace()
    fun onSpace()
    fun onEnter()
}
