package com.foscreener.app

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable fun PaperAutoPanel(repository:Repository) {
    var status by remember { mutableStateOf<JSONObject?>(null) }
    var symbol by remember { mutableStateOf("AAPL") }
    var timeframe by remember { mutableStateOf("5m") }
    var error by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val scope=rememberCoroutineScope()
    LaunchedEffect(Unit) {
        while(true) {
            try { status=JSONObject(repository.request("/paper-auto"));error="" }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) { error=e.message?:"Paper monitor unavailable" }
            delay(15000)
        }
    }
    fun setEnabled(enabled:Boolean) { scope.launch {
        busy=true
        try {
            val body=JSONObject().put("enabled",enabled)
            if(enabled) body.put("symbol",symbol.trim().uppercase()).put("timeframe",timeframe).put("capital",1000).put("risk_pct",0.5).put("rr",2)
            status=JSONObject(repository.request("/paper-auto","POST",body));error=""
        } catch(e:CancellationException) { throw e }
          catch(e:Exception) { error=e.message?:"Request failed" }
        finally { busy=false }
    } }
    Card { Column(Modifier.fillMaxWidth().padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
        Text("Automatic paper scalping",style=MaterialTheme.typography.titleLarge)
        Text("Delayed data only · No broker orders",fontSize=12.sp)
        Text("$1,000 simulated balance · 0.5% risk (initially $5) · $20 daily loss limit · one open position · max 30-minute hold · max 10 entries/day · stop after 3 consecutive losses.",fontSize=12.sp)
        Text("Long-only stocks/ETFs; regular US session entries only. Futures and shorts skipped. New completed bars only; next-bar-open simulated entry, conservative stop-first exits. Delayed data cannot establish real scalping performance.",fontSize=11.sp)
        OutlinedTextField(symbol,{symbol=it.uppercase()},singleLine=true,label={Text("Stock / ETF symbol")},enabled=status?.optBoolean("enabled")!=true)
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) { listOf("5m","15m").forEach { tf -> FilterChip(selected=timeframe==tf,onClick={timeframe=tf},enabled=status?.optBoolean("enabled")!=true,label={Text(tf)}) } }
        Button(onClick={setEnabled(true)},enabled=!busy && status?.optBoolean("enabled")!=true) { Text("Start delayed paper monitor") }
        OutlinedButton(onClick={setEnabled(false)},enabled=!busy && status?.optBoolean("enabled")==true) { Text("Pause paper monitor") }
        if(error.isNotEmpty()) Text(error,color=MaterialTheme.colorScheme.error,fontSize=12.sp)
        status?.let { p ->
            Text("${if(p.optBoolean("enabled")) "PAPER MONITOR ON" else "PAPER MONITOR OFF"} · ${p.optString("reason")}",fontSize=12.sp)
            p.optJSONObject("risk")?.let { r -> Text("Balance ${r.money("balance","USD")} · Day P&L ${r.money("day_pnl","USD")} (UTC)",fontSize=12.sp) }
            p.optJSONArray("trades")?.objects()?.takeLast(5)?.reversed()?.forEach { t -> Text("PAPER ${t.optString("symbol")} · ${t.optString("state")}\nEntry ${t.money("entry")} · Stop ${t.money("stop")} · Target ${t.money("target")}\nExit ${t.money("exit_price")} · net simulated P&L ${t.money("pnl")}",fontSize=12.sp) }
        }
        Text("Target: 2R net under the fee model. Illustrative round-trip fees: $2 + $0.01/share. No slippage model. Gaps can exceed risk limits. Pause/restart leaves unresolved simulations without fabricated exits.",fontSize=11.sp)
    } }
}
