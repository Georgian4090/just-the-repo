package com.homelab.ledcountdown

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import android.widget.RemoteViews

class CountdownWidgetProvider : AppWidgetProvider() {

    companion object {
        const val ACTION_TARGET_REACHED = "com.homelab.ledcountdown.ACTION_TARGET_REACHED"
        const val ACTION_REFRESH = "com.homelab.ledcountdown.ACTION_REFRESH"

        /**
         * Builds and pushes the RemoteViews for one widget instance based on
         * whatever target time is currently saved in prefs for that widget id.
         */
        fun updateAppWidget(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int) {
            val views = RemoteViews(context.packageName, R.layout.countdown_widget)
            val targetMillis = WidgetPrefs.loadTargetMillis(context, appWidgetId)
            val label = WidgetPrefs.loadLabel(context, appWidgetId)

            views.setTextViewText(R.id.widget_label, if (label.isBlank()) context.getString(R.string.default_label) else label)

            if (targetMillis <= 0L) {
                // Not configured yet
                views.setViewVisibility(R.id.widget_chronometer, android.view.View.GONE)
                views.setViewVisibility(R.id.widget_reached, android.view.View.GONE)
                views.setTextViewText(R.id.widget_label, context.getString(R.string.tap_to_configure))
            } else {
                val now = System.currentTimeMillis()
                if (targetMillis <= now) {
                    // Target already passed -> show static "reached" state
                    views.setViewVisibility(R.id.widget_chronometer, android.view.View.GONE)
                    views.setViewVisibility(R.id.widget_reached, android.view.View.VISIBLE)
                } else {
                    val base = SystemClock.elapsedRealtime() + (targetMillis - now)
                    views.setViewVisibility(R.id.widget_reached, android.view.View.GONE)
                    views.setViewVisibility(R.id.widget_chronometer, android.view.View.VISIBLE)
                    views.setChronometer(R.id.widget_chronometer, base, null, true)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                        views.setChronometerCountDown(R.id.widget_chronometer, true)
                    }
                    scheduleCompletionAlarm(context, appWidgetId, targetMillis)
                }
            }

            // Tapping the widget opens the configure screen so the target/label can be edited.
            val configIntent = Intent(context, WidgetConfigureActivity::class.java).apply {
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
            val pendingIntent = PendingIntent.getActivity(
                context, appWidgetId, configIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.widget_root, pendingIntent)

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }

        /**
         * Schedules a single exact alarm for the moment the countdown hits zero, so the
         * widget flips to the "reached" state right on time instead of waiting for the
         * next periodic system update (which can be up to 30 minutes later).
         */
        private fun scheduleCompletionAlarm(context: Context, appWidgetId: Int, targetMillis: Long) {
            val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            val intent = Intent(context, CountdownWidgetProvider::class.java).apply {
                action = ACTION_TARGET_REACHED
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
            }
            val pendingIntent = PendingIntent.getBroadcast(
                context, appWidgetId, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                if (alarmManager.canScheduleExactAlarms()) {
                    alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, targetMillis + 500, pendingIntent)
                } else {
                    alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, targetMillis + 500, pendingIntent)
                }
            } else {
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, targetMillis + 500, pendingIntent)
            }
        }
    }

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (id in appWidgetIds) {
            updateAppWidget(context, appWidgetManager, id)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_TARGET_REACHED || intent.action == ACTION_REFRESH) {
            val appWidgetId = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
            val appWidgetManager = AppWidgetManager.getInstance(context)
            if (appWidgetId != AppWidgetManager.INVALID_APPWIDGET_ID) {
                updateAppWidget(context, appWidgetManager, appWidgetId)
            } else {
                val ids = appWidgetManager.getAppWidgetIds(
                    android.content.ComponentName(context, CountdownWidgetProvider::class.java)
                )
                for (id in ids) updateAppWidget(context, appWidgetManager, id)
            }
        }
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        for (id in appWidgetIds) {
            WidgetPrefs.deleteTarget(context, id)
        }
    }
}
