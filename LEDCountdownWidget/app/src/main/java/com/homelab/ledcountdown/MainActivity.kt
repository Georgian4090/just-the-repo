package com.homelab.ledcountdown

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val tv = TextView(this).apply {
            text = getString(R.string.main_activity_instructions)
            textSize = 16f
            setPadding(48, 96, 48, 48)
        }
        setContentView(tv)
    }
}
