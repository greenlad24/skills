package com.stagemix.app

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.stagemix.app.ui.StageMixApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // A mixer console never sleeps mid-show; screen-on also keeps the
        // low-latency Wi-Fi lock honored and Doze away (see checklist).
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        AppState.load(this)
        setContent { StageMixApp() }
    }
}
