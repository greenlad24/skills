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
        // SHOWING THE APP WITHOUT A BAND.
        //
        // Every screen past the first needs sixteen channels of live
        // meter off a console that is only ever in one room, so there
        // was no way to look at this thing away from a gig — or to
        // photograph it. `--ez demo true` drives the whole screen from
        // a synthetic band. It cannot reach a mixer: see DemoStage.
        if (intent?.getBooleanExtra("demo", false) == true) {
            DemoStage.stop()
            AppState.startTab = intent?.getIntExtra("tab", 0) ?: 0
            DemoStage.start(
                directing = intent?.getBooleanExtra("mixing", true) != false)
        }
        setContent { StageMixApp() }
    }
}
