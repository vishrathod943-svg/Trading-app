package com.foscreener.app

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject

@Composable fun AutomationPanel(vm: CompassViewModel, s: CompassState, capital: String, risk: String) {
    val broker=s.broker
    val auto=s.automation
    var mode by remember(auto?.optString("mode")) { mutableStateOf(auto?.optString("mode")?:"paper") }
    var rr by remember(auto?.optDouble("rr")) { mutableStateOf(auto?.optString("rr","3")?:"3") }
    var daily by remember(auto?.optDouble("daily_loss_pct")) { mutableStateOf(auto?.optString("daily_loss_pct","3")?:"3") }
    var max by remember(auto?.optInt("max_positions")) { mutableStateOf(auto?.optString("max_positions","3")?:"3") }
    var stop by remember(auto?.optDouble("premium_stop_pct")) { mutableStateOf(auto?.optString("premium_stop_pct","25")?:"25") }
    var confirm by remember { mutableStateOf(false) }
    var phrase by remember { mutableStateOf("") }
    val ready=broker?.optBoolean("ready")==true && s.connected && !s.stale
    val enabled=auto?.optBoolean("enabled")==true
    Card { Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text("Kite connection & automation",fontSize=20.sp,fontWeight=FontWeight.Bold)
        Text(if(broker?.optString("mode")=="kite") "${broker.optInt("analysed_count")} / ${broker.optInt("universe_count")} symbols analysed · ${if(ready) "Ready" else "Not ready"}" else "Connect a Kite backend to continue",fontSize=12.sp)
        Text("Last broker tick: ${if(broker==null || broker.isNull("tick_age_ms")) "—" else "${broker.optLong("tick_age_ms")} ms ago"}",fontSize=12.sp)
        Text("Updates arrive with the broker feed. This is not a millisecond execution guarantee.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            FilterChip(selected=mode=="paper",onClick={mode="paper"},enabled=!enabled,label={Text("Paper automation")})
            FilterChip(selected=mode=="live",onClick={mode="live"},enabled=!enabled && auto?.optBoolean("live_allowed")==true,label={Text("Real orders")})
        }
        OutlinedTextField(rr,{rr=it},label={Text("Option premium target R:R (2–10)")},singleLine=true,enabled=!enabled,modifier=Modifier.fillMaxWidth())
        OutlinedTextField(stop,{stop=it},label={Text("Option premium stop % (5–50)")},singleLine=true,enabled=!enabled,modifier=Modifier.fillMaxWidth())
        OutlinedTextField(max,{max=it},label={Text("Maximum positions (1–5)")},singleLine=true,enabled=!enabled,modifier=Modifier.fillMaxWidth())
        OutlinedTextField(daily,{daily=it},label={Text("Daily loss / committed premium limit % (0–5)")},singleLine=true,enabled=!enabled,modifier=Modifier.fillMaxWidth())
        Text("Budget ₹$capital · risk $risk% · buys one liquid CE/PE lot only if its entire premium fits the risk budget. R:R is on premium, not the stock price. Costs and gaps can change realized R:R.",fontSize=12.sp)
        Row(horizontalArrangement=Arrangement.SpaceBetween,modifier=Modifier.fillMaxWidth()) {
            Text(if(enabled) "Auto-trading ON · ${auto?.optString("mode")}" else "Auto-trading OFF",fontWeight=FontWeight.Bold)
            Switch(checked=enabled,onCheckedChange={ if(it) {phrase="";confirm=true} else vm.action("/automation/stop") },enabled=enabled || ready)
        }
        Text(auto?.optString("reason")?:"Waiting for server",fontSize=12.sp)
        OutlinedButton(onClick={vm.action("/automation/stop")},modifier=Modifier.fillMaxWidth()) { Text("Stop new entries") }
        Text("Stopping prevents new submissions. Pending broker orders and open positions are NOT cancelled or closed. Protective orders continue. Check Zerodha to cancel orders or exit positions.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        val orders=auto?.optJSONArray("orders")?.objects()?:emptyList()
        orders.take(10).forEach { o ->
            HorizontalDivider()
            Text("${o.optString("contract")} · ${o.optString("mode").uppercase()} · ${o.optString("state")}",fontSize=12.sp,fontWeight=FontWeight.SemiBold)
            Text("Qty ${o.optInt("quantity")} · Entry ${o.money("fill")}\nSL ${o.money("stop")} · Target ${o.money("target")}",fontSize=11.sp)
            if(!o.isNull("pnl")) Text("Realized ${o.money("pnl")} before costs",fontSize=12.sp)
        }
    } }
    if(confirm) AlertDialog(onDismissRequest={confirm=false},title={Text(if(mode=="live") "Enable real automatic orders?" else "Enable paper automation?")},text={
        Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {
            Text("The server monitors completed-day setups and live entries even when the phone is closed. Capital ₹$capital, risk $risk%, target ${rr}R. Broker session and the server must remain available.")
            if(mode=="live") { Text("Real money is at risk. Type ENABLE LIVE ORDERS to confirm."); OutlinedTextField(phrase,{phrase=it},singleLine=true) }
        }
    },confirmButton={TextButton(enabled=mode!="live" || phrase=="ENABLE LIVE ORDERS",onClick={
        val c=capital.toDoubleOrNull();val r=risk.toDoubleOrNull();val reward=rr.toDoubleOrNull();val count=max.toIntOrNull();val loss=daily.toDoubleOrNull();val sl=stop.toDoubleOrNull()
        if(c!=null && r!=null && reward!=null && count!=null && loss!=null && sl!=null && listOf(c,r,reward,loss,sl).all { it.isFinite() }) {
            vm.action("/automation",JSONObject().put("enabled",true).put("mode",mode).put("capital",c).put("risk_pct",r).put("rr",reward).put("max_positions",count).put("daily_loss_pct",loss).put("premium_stop_pct",sl).put("confirmation",phrase))
            confirm=false
        }
    }) {Text("Enable ${if(mode=="live") "real orders" else "paper"}")} },dismissButton={TextButton(onClick={confirm=false}) {Text("Cancel")}})
}
