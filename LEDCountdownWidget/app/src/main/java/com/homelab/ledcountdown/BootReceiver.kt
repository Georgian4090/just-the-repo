package com.homelab.ledcountdown

import android.appwidget.AppWidgetManager
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            val appWidgetManager = AppWidgetManager.getInstance(context)
            val ids = appWidgetManager.getAppWidgetIds(
                ComponentName(context, CountdownWidgetProvider::class.java)
            )
            for (id in ids) {
                CountdownWidgetProvider.updateAppWidget(context, appWidgetManager, id)
            }
        }
    }
}
