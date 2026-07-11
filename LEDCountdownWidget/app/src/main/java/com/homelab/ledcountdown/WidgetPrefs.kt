package com.homelab.ledcountdown

import android.content.Context

/**
 * Persists the target date/time and label per widget instance (keyed by appWidgetId),
 * so the countdown survives reboots, process death, and widget resizes.
 */
object WidgetPrefs {

    private const val PREFS_NAME = "com.homelab.ledcountdown.WIDGET_PREFS"
    private const val KEY_TARGET_MILLIS = "target_millis_"
    private const val KEY_LABEL = "label_"

    fun saveTarget(context: Context, appWidgetId: Int, targetMillis: Long, label: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit()
            .putLong(KEY_TARGET_MILLIS + appWidgetId, targetMillis)
            .putString(KEY_LABEL + appWidgetId, label)
            .apply()
    }

    fun loadTargetMillis(context: Context, appWidgetId: Int): Long {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getLong(KEY_TARGET_MILLIS + appWidgetId, -1L)
    }

    fun loadLabel(context: Context, appWidgetId: Int): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_LABEL + appWidgetId, "") ?: ""
    }

    fun deleteTarget(context: Context, appWidgetId: Int) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit()
            .remove(KEY_TARGET_MILLIS + appWidgetId)
            .remove(KEY_LABEL + appWidgetId)
            .apply()
    }
}
