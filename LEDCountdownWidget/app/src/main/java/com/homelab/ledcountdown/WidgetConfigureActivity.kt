package com.homelab.ledcountdown

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.DatePicker
import android.widget.EditText
import android.widget.TimePicker
import android.widget.Toast
import java.util.Calendar

class WidgetConfigureActivity : Activity() {

    private var appWidgetId = AppWidgetManager.INVALID_APPWIDGET_ID

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // If the widget host cancels, nothing is created.
        setResult(RESULT_CANCELED)
        setContentView(R.layout.activity_widget_configure)

        appWidgetId = intent?.extras?.getInt(
            AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID
        ) ?: AppWidgetManager.INVALID_APPWIDGET_ID

        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            finish()
            return
        }

        val labelInput = findViewById<EditText>(R.id.input_label)
        val datePicker = findViewById<DatePicker>(R.id.date_picker)
        val timePicker = findViewById<TimePicker>(R.id.time_picker)
        val saveButton = findViewById<Button>(R.id.button_save)

        timePicker.setIs24HourView(true)

        // Pre-fill with existing values if this widget was already configured (tap-to-edit).
        val existingTarget = WidgetPrefs.loadTargetMillis(this, appWidgetId)
        val existingLabel = WidgetPrefs.loadLabel(this, appWidgetId)
        if (existingTarget > 0) {
            val cal = Calendar.getInstance().apply { timeInMillis = existingTarget }
            datePicker.updateDate(
                cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)
            )
            timePicker.hour = cal.get(Calendar.HOUR_OF_DAY)
            timePicker.minute = cal.get(Calendar.MINUTE)
            labelInput.setText(existingLabel)
        } else {
            // Default to one week from now so the picker isn't sitting on a past date.
            val cal = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, 7) }
            datePicker.updateDate(
                cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)
            )
        }

        saveButton.setOnClickListener {
            val cal = Calendar.getInstance()
            cal.set(
                datePicker.year, datePicker.month, datePicker.dayOfMonth,
                timePicker.hour, timePicker.minute, 0
            )
            cal.set(Calendar.MILLISECOND, 0)
            val targetMillis = cal.timeInMillis

            if (targetMillis <= System.currentTimeMillis()) {
                Toast.makeText(this, R.string.error_past_date, Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            WidgetPrefs.saveTarget(this, appWidgetId, targetMillis, labelInput.text.toString().trim())

            val appWidgetManager = AppWidgetManager.getInstance(this)
            CountdownWidgetProvider.updateAppWidget(this, appWidgetManager, appWidgetId)

            val resultValue = Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
            setResult(RESULT_OK, resultValue)
            finish()
        }
    }
}
