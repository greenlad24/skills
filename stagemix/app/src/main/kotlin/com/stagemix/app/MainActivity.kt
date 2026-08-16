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
        AppState.loadSwitches(this)
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
        // OPEN IT AND IT GOES.
        //
        // No IP to type, no button to find in the dark: it broadcasts
        // for the desk on the mixer's own Wi-Fi and, once it answers,
        // takes the mains by itself (MixerService does that half). The
        // saved IP is tried first and discovery is the fallback, so a
        // rig that always uses the same address connects instantly.
        else if (AppState.autoStart.value &&
                 AppState.conn.value == AppState.Conn.DISCONNECTED) {
            MixerService.cmd(this, MixerService.ACTION_CONNECT,
                "ip" to AppState.config.value.mixerIp)
        }
        setContent { StageMixApp() }
    }
}
