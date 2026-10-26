package com.foscreener.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ShowChart
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import org.json.JSONObject
import kotlin.math.abs

private val Mint = Color(0xFFC1F17C)
private val Ink = Color(0xFF111811)
private val Rose = Color(0xFFFF8B87)
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val dark = isSystemInDarkTheme()
            MaterialTheme(colorScheme = if (dark) darkColorScheme(primary=Mint, onPrimary=Ink, background=Color(0xFF101511), surface=Color(0xFF182019), surfaceVariant=Color(0xFF232D24)) else lightColorScheme(primary=Color(0xFF3C681E), onPrimary=Color.White, background=Color(0xFFF5F7F0), surface=Color.White, surfaceVariant=Color(0xFFE8EEDE))) {
                CompassApp()
            }
        }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun CompassApp(vm: CompassViewModel = viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    var accepted by remember { mutableStateOf(vm.repository.accepted) }
    var tab by remember { mutableIntStateOf(0) }
    var selected by remember { mutableStateOf<String?>(null) }
    val snack = remember { SnackbarHostState() }
    LaunchedEffect(state.message) { state.message?.let { snack.showSnackbar(it); vm.dismissMessage() } }
    BackHandler(selected != null) { selected = null }
    if (!accepted) {
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.padding(28.dp).safeDrawingPadding(), verticalArrangement=Arrangement.Center) {
                Icon(Icons.Outlined.Explore, null, Modifier.size(64.dp), tint=MaterialTheme.colorScheme.primary)
                Spacer(Modifier.height(24.dp)); Text("Know your setup.\nRespect your risk.", fontSize=34.sp, fontWeight=FontWeight.Bold)
                Spacer(Modifier.height(20.dp)); Text("F&O COMPASS", color=MaterialTheme.colorScheme.primary, letterSpacing=3.sp)
                Spacer(Modifier.height(24.dp)); Text("Educational tool. Not investment advice. Trading in F&O involves substantial risk, including loss of the entire premium. Alerts can be delayed and actual fills can differ.")
                Spacer(Modifier.height(16.dp)); Text("Demo uses synthetic prices. A Kite backend can supply live quotes. Real orders require server permission and your explicit auto-trading confirmation. Background push is not connected.", color=MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(32.dp)); Button(onClick={vm.repository.accepted=true;accepted=true},Modifier.fillMaxWidth()) { Text("I understand · Explore demo") }
            }
        }; return
    }
    Scaffold(
        topBar={ TopAppBar(title={ Column { Text(if(selected!=null) selected!! else "F&O COMPASS",fontWeight=FontWeight.Bold,letterSpacing=1.sp); Text("RESEARCH / PLAN / TRACK",fontSize=10.sp,letterSpacing=2.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) } }, navigationIcon={ if(selected!=null) IconButton(onClick={selected=null}) { Icon(Icons.AutoMirrored.Outlined.ArrowBack,"Back") } },actions={IconButton(onClick={vm.refresh()}) { Icon(Icons.Outlined.Refresh,"Refresh") }}) },
        bottomBar={ if(selected==null) NavigationBar { listOf("Overview","Screener","Trades","Alerts","Settings").forEachIndexed { i,label -> NavigationBarItem(selected=tab==i,onClick={tab=i},icon={Icon(listOf(Icons.Outlined.Dashboard,Icons.Outlined.Tune,Icons.AutoMirrored.Outlined.ShowChart,Icons.Outlined.Notifications,Icons.Outlined.Settings)[i],label)},label={Text(label,fontSize=10.sp)}) } } },
        snackbarHost={SnackbarHost(snack)}
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(horizontal=16.dp,vertical=8.dp),verticalAlignment=Alignment.CenterVertically) {
                Icon(Icons.Outlined.Science,null,Modifier.size(15.dp)); Spacer(Modifier.width(8.dp))
                Text(if(state.scan?.optString("mode")=="kite") "KITE · BROKER DATA" else if(vm.repository.requireLive) "KITE · DISCONNECTED" else "DEMO · SYNTHETIC PRICES",fontSize=10.sp,fontWeight=FontWeight.Bold,modifier=Modifier.weight(1f))
                Text(if(state.stale) "OFFLINE / STALE" else if(state.connected) "CONNECTED" else "SNAPSHOT",fontSize=9.sp)
            }
            if(state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            state.error?.let { Text(it,Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.errorContainer).padding(12.dp),color=MaterialTheme.colorScheme.onErrorContainer,fontSize=12.sp) }
            val open: (String)->Unit = { selected=it;vm.detail(it) }
            if(selected!=null) Detail(state,vm) else when(tab) {
                0 -> Overview(state,open,{tab=1},{vm.action("/replay/demo")})
                1 -> Screener(state,open)
                2 -> Trades(state,vm)
                3 -> Alerts(state)
                else -> Settings(vm)
            }
        }
    }
}
@Composable private fun Label(text: String) { Text(text.uppercase(),fontSize=10.sp,letterSpacing=1.5.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,fontWeight=FontWeight.SemiBold) }
@Composable private fun Metric(label: String,value: String,modifier: Modifier=Modifier) {
    Card(modifier) { Column(Modifier.padding(18.dp)) { Label(label); Spacer(Modifier.height(10.dp)); Text(value,fontSize=29.sp,fontWeight=FontWeight.SemiBold) } }
}
@Composable private fun Empty(title:String,body:String) { Column(Modifier.fillMaxWidth().padding(vertical=24.dp),horizontalAlignment=Alignment.CenterHorizontally) { Icon(Icons.Outlined.Search,null,Modifier.size(32.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant); Spacer(Modifier.height(12.dp)); Text(title,fontWeight=FontWeight.SemiBold); Text(body,Modifier.padding(top=6.dp),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
@Composable private fun Overview(s:CompassState,open:(String)->Unit,all:()->Unit,replay:()->Unit) {
    val scan=s.scan
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        item { Row(verticalAlignment=Alignment.CenterVertically) { Column(Modifier.weight(1f)) { Label("Your market workspace"); Text("The opportunity radar",fontSize=26.sp,fontWeight=FontWeight.Bold,modifier=Modifier.padding(top=6.dp)) }; Icon(Icons.Outlined.NorthEast,null,tint=MaterialTheme.colorScheme.primary) } }
        item { Card(colors=CardDefaults.cardColors(containerColor=Mint,contentColor=Ink)) { Column(Modifier.padding(22.dp)) { Text("DISCIPLINE BEFORE DIRECTION",fontSize=10.sp,letterSpacing=1.5.sp); Text("A clear plan.\nA defined risk.",fontSize=31.sp,lineHeight=37.sp,fontWeight=FontWeight.Bold,modifier=Modifier.padding(vertical=14.dp)); Text("Explore setups with context, not promises.",fontSize=13.sp) } } }
        item { Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) { Metric("Confirmed",scan?.optInt("confirmed_count")?.toString()?:"—",Modifier.weight(1f)); Metric("Average score",scan?.optDouble("average_score")?.let { "%.0f".format(it) }?:"—",Modifier.weight(1f)) } }
        item { Card { Column(Modifier.padding(18.dp)) { Label(if(scan?.optString("mode")=="kite") "Analysed universe breadth · last closed day" else "Demo market breadth"); Spacer(Modifier.height(14.dp)); Row { Text("↑ ${scan?.optInt("advances")?:0} advancing",Modifier.weight(1f),color=MaterialTheme.colorScheme.primary); Text("↓ ${scan?.optInt("declines")?:0} declining",color=MaterialTheme.colorScheme.error) }; Text(if(scan?.optString("mode")=="kite") "${scan.optJSONArray("items")?.length()?:0} analysed Kite symbols" else "8 synthetic NSE symbols · BSE unavailable",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,modifier=Modifier.padding(top=10.dp)) } } }
        item { Row(verticalAlignment=Alignment.CenterVertically) { Text("On the radar",fontSize=20.sp,fontWeight=FontWeight.SemiBold,modifier=Modifier.weight(1f)); TextButton(onClick=all) { Text("View all →") } } }
        val items=scan?.optJSONArray("items")?.objects()?.sortedByDescending { it.optInt("score") }?.take(3)?:emptyList()
        if(items.isEmpty()) item { Empty("Waiting for the backend","Start the server, then tap Refresh.") }
        items(items) { SetupRow(it,open) }
        if(scan?.optString("mode")!="kite") item { OutlinedButton(onClick=replay,modifier=Modifier.fillMaxWidth()) { Icon(Icons.Outlined.PlayArrow,null); Spacer(Modifier.width(8.dp)); Text("Run paper alert replay") } }
        if(scan?.optString("mode")!="kite") item { Text("Replay creates an isolated DEMO trade and triggers entry, T1 and T2. No orders are placed.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        item { Text("Fetched: ${scan?.optString("updated_at")?:"—"}\nDaily indicator dates are shown per stock. Live LTP is streamed separately; no fixed update interval is guaranteed.",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
@Composable private fun SetupRow(item:JSONObject,open:(String)->Unit) {
    Card(Modifier.fillMaxWidth().clickable { open(item.getString("symbol")) }) {
        Row(Modifier.padding(16.dp),verticalAlignment=Alignment.CenterVertically) {
            Surface(shape=RoundedCornerShape(12.dp),color=MaterialTheme.colorScheme.surfaceVariant) { Text(item.getString("symbol").take(2),Modifier.padding(12.dp),fontWeight=FontWeight.Bold) }
            Column(Modifier.weight(1f).padding(horizontal=12.dp)) { Text(item.getString("symbol"),fontWeight=FontWeight.SemiBold); Text("${item.optString("sector")} · ${item.optString("direction")}",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
            Column(horizontalAlignment=Alignment.End) { Text(item.money("price"),fontWeight=FontWeight.Medium); Text("Score ${item.optInt("score")} / 100",fontSize=11.sp,color=MaterialTheme.colorScheme.primary) }
        }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun Screener(s:CompassState,open:(String)->Unit) {
    var search by remember { mutableStateOf("") }; var exchange by remember { mutableStateOf("All") }; var direction by remember { mutableStateOf("All") }; var threshold by remember { mutableFloatStateOf(0f) }; var confirmed by remember { mutableStateOf(false) }; var sort by remember { mutableStateOf(true) }
    val rows=s.scan?.optJSONArray("items")?.objects()?.filter { it.getString("symbol").contains(search,true) && (exchange=="All" || it.optString("exchange")==exchange) && (direction=="All" || it.optString("direction")==direction) && it.optInt("score")>=threshold && (!confirmed || it.optBoolean("confirmed")) }?.let { if(sort) it.sortedByDescending { x->x.optInt("score") } else it.sortedBy { x->x.getString("symbol") } }?:emptyList()
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        item { Text("Find your next setup",fontSize=26.sp,fontWeight=FontWeight.Bold) }
        item { OutlinedTextField(search,{search=it},label={Text("Search symbol")},leadingIcon={Icon(Icons.Outlined.Search,null)},singleLine=true,modifier=Modifier.fillMaxWidth()) }
        item { Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) { listOf("All","NSE","BSE").forEach { FilterChip(selected=exchange==it,onClick={exchange=it},label={Text(it)}) } } }
        item { Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) { listOf("All","LONG","SHORT","WATCH").forEach { FilterChip(selected=direction==it,onClick={direction=it},label={Text(it,fontSize=11.sp)}) } } }
        item { Label("Minimum score: ${threshold.toInt()}"); Slider(threshold,{threshold=it},valueRange=0f..100f,steps=19) }
        item { Row(verticalAlignment=Alignment.CenterVertically) { Checkbox(confirmed,{confirmed=it}); Text("Confirmed only",Modifier.weight(1f)); TextButton(onClick={sort=!sort}) { Text(if(sort) "Score ↓" else "A–Z") } } }
        item { Label("${rows.size} results · ${if(exchange=="BSE") "BSE provider not connected" else if(s.scan?.optString("mode")=="kite") "Kite scanned universe" else "Synthetic sample universe"}") }
        if(rows.isEmpty()) item { Empty("No matching setups","Try lowering the score or changing filters.") }
        items(rows) { SetupRow(it,open) }
    }
}
@Composable private fun Detail(s:CompassState,vm:CompassViewModel) {
    val d=s.detail ?: return
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
        item { Label("${d.optString("exchange")} / ${d.optString("sector")}"); Text(d.money("price"),fontSize=38.sp,fontWeight=FontWeight.Bold); Text("${d.optDouble("change_pct")}% last closed session · ${d.optString("data_as_of")}",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        item { Card { Column(Modifier.padding(16.dp)) { Label("Daily price & volume · 80 closed sessions"); Candles(d.getJSONArray("candles").objects()) } } }
        item { Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) { Metric("Setup score", "${d.optInt("score")}",Modifier.weight(1f)); Metric("Volume ratio","${d.optDouble("volume_ratio")}×",Modifier.weight(1f)) } }
        item { Text(if(d.optBoolean("confirmed")) "Confirmed ${d.optString("direction")} setup" else "Watchlist · no confirmed trade",fontSize=20.sp,fontWeight=FontWeight.Bold) }
        val indicators=d.getJSONObject("indicators")
        item { Card { Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(9.dp)) { Label("Technical context"); listOf("ema20","ema50","ema200","rsi","atr","macd","high20","low20").forEach { key -> Row { Text(key.uppercase(),Modifier.weight(1f),fontSize=12.sp); Text("%.2f".format(indicators.optDouble(key)),fontSize=12.sp) } } } } }
        if(!d.isNull("plan")) item { val p=d.getJSONObject("plan"); Card { Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) { Label("Underlying trade plan"); listOf("entry","pullback","stop","target1","target2").forEach { Text("${it.uppercase()}  ${p.money(it)}") }; Text("Target 2 risk / reward: 3R"); Button(onClick={vm.action("/trades",JSONObject().put("symbol",d.getString("symbol")).put("capital",vm.repository.capital.toDoubleOrNull()?:100000.0).put("risk_pct",vm.repository.risk.toDoubleOrNull()?:1.0))},enabled=!s.stale) { Text("Track paper trade") } } } }
        item { Label("Out-of-sample backtest · underlying returns") }
        items(d.getJSONArray("backtests").objects()) { b -> Card { Column(Modifier.fillMaxWidth().padding(16.dp)) { Text("${b.optInt("horizon")}-day hold · ${b.optInt("sample_size")} samples",fontWeight=FontWeight.SemiBold); Text(if(b.optBoolean("statistics_available")) "Win ${b.optDouble("win_rate")}% · Avg ${b.optDouble("average_return")}% · ${b.optDouble("average_r")}R" else "Statistics hidden: fewer than 20 observations",fontSize=12.sp); Text("25 bps costs · chronological holdout",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) } } }
        item { Label("Recent major moves") }
        val moves=d.getJSONArray("major_moves").objects()
        if(moves.isEmpty()) item { Text("No qualifying moves in this sample.",fontSize=12.sp) }
        items(moves) { Text("${it.optString("date")} · ${it.optDouble("change_pct")}% · ${it.optDouble("volume_ratio")}× volume",fontSize=12.sp) }
        item { Card { Column(Modifier.padding(16.dp)) { Label("Options & fundamentals"); Text("Unavailable in demo",fontSize=20.sp,modifier=Modifier.padding(vertical=8.dp)); Text("Connect a licensed broker adapter before selecting strikes, expiries or premiums. No option recommendation is fabricated.",fontSize=12.sp) } } }
    }
}
@Composable private fun Candles(candles:List<JSONObject>) {
    Canvas(Modifier.fillMaxWidth().height(220.dp).padding(top=18.dp)) {
        if(candles.isEmpty()) return@Canvas
        val high=candles.maxOf { it.getDouble("high") }; val low=candles.minOf { it.getDouble("low") }; val range=(high-low).coerceAtLeast(.01)
        val step=size.width/candles.size; val priceHeight=size.height*.76f
        fun y(p:Double)=((high-p)/range*priceHeight).toFloat()
        val maxV=candles.maxOf { it.getDouble("volume") }
        repeat(4) { n -> val gy=priceHeight*n/3; drawLine(Color.Gray.copy(alpha=.15f),Offset(0f,gy),Offset(size.width,gy)) }
        candles.forEachIndexed { n,c ->
            val x=(n+.5f)*step; val color=if(c.getDouble("close")>=c.getDouble("open")) Color(0xFF83C963) else Rose
            drawLine(color,Offset(x,y(c.getDouble("high"))),Offset(x,y(c.getDouble("low"))),1f)
            drawLine(color,Offset(x,y(c.getDouble("open"))),Offset(x,y(c.getDouble("close"))+.8f),step*.65f)
            drawLine(color.copy(alpha=.4f),Offset(x,size.height),Offset(x,size.height-(c.getDouble("volume")/maxV*size.height*.18f).toFloat()),step*.65f)
        }
    }
}
@Composable private fun Trades(s:CompassState,vm:CompassViewModel) {
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
        item { Text("Your paper desk",fontSize=26.sp,fontWeight=FontWeight.Bold); Text("No real orders · maximum 5 active trades",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        if(s.trades.isEmpty()) item { Empty("No tracked trades","Use Overview → Run paper alert replay.") }
        items(s.trades) { t -> Card { Column(Modifier.fillMaxWidth().padding(18.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) { Row { Text(t.getString("symbol"),fontSize=20.sp,fontWeight=FontWeight.Bold,modifier=Modifier.weight(1f)); Text(t.optString("direction"),color=MaterialTheme.colorScheme.primary) }; Label(t.optString("state").replace('_',' ')); Text("Entry ${t.money("entry")} · Last ${t.money("last_price")}",fontSize=12.sp); Text("SL ${t.money("stop")} · T1 ${t.money("target1")} · T2 ${t.money("target2")}",fontSize=11.sp); Text("Quantity: ${t.optInt("quantity")} · Underlying only",fontSize=11.sp); if(!t.isNull("pnl")) Text("${t.optString("pnl_kind").replaceFirstChar { it.uppercase() }} P&L: ${t.money("pnl")} · before costs",fontSize=12.sp,color=MaterialTheme.colorScheme.primary); if(t.optString("state") in listOf("WAITING_ENTRY","ENTRY_TRIGGERED","T1_HIT")) OutlinedButton(onClick={vm.action("/trades/${t.getInt("id")}",method="DELETE")}) { Text("Stop tracking") } } } }
    }
}
@Composable private fun Alerts(s:CompassState) {
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        item { Text("Signal journal",fontSize=26.sp,fontWeight=FontWeight.Bold); Text("In-app replay events · background push not connected",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        if(s.alerts.isEmpty()) item { Empty("All quiet","Replay a paper trade to test the alert lifecycle.") }
        items(s.alerts) { a -> Card { Row(Modifier.padding(16.dp)) { Icon(Icons.Outlined.NotificationsActive,null,tint=MaterialTheme.colorScheme.primary); Column(Modifier.padding(start=12.dp)) { Text("${a.optString("symbol")} · ${a.optString("event").replace('_',' ')}",fontWeight=FontWeight.SemiBold,fontSize=13.sp); Text(a.optString("message"),fontSize=12.sp,modifier=Modifier.padding(vertical=6.dp)); Text("${a.money("price")} · ${a.optString("time")}",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) } } } }
    }
}
@Composable private fun Settings(vm:CompassViewModel) {
    val server by vm.state.collectAsStateWithLifecycle()
    var token by remember { mutableStateOf(vm.repository.apiToken) }
    var liveMode by remember { mutableStateOf(vm.repository.requireLive) }
    var url by remember { mutableStateOf(vm.repository.baseUrl) }; var capital by remember { mutableStateOf(vm.repository.capital) }; var risk by remember { mutableStateOf(vm.repository.risk) }; var error by remember { mutableStateOf<String?>(null) }; var saved by remember { mutableStateOf(false) }
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        item { Text("Set your boundaries",fontSize=26.sp,fontWeight=FontWeight.Bold) }
        item { Label("Risk preferences"); Text("Used for underlying paper-trade position sizing. Option lot sizing requires verified contracts.",fontSize=12.sp) }
        item { OutlinedTextField(capital,{capital=it;saved=false},label={Text("Capital (₹)")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Decimal),modifier=Modifier.fillMaxWidth(),singleLine=true) }
        item { OutlinedTextField(risk,{risk=it;saved=false},label={Text("Risk per trade (0–2%)")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Decimal),modifier=Modifier.fillMaxWidth(),singleLine=true) }
        item { Label("Backend connection"); OutlinedTextField(url,{url=it;saved=false},label={Text("API base URL")},modifier=Modifier.fillMaxWidth(),singleLine=true); Text("Emulator: http://10.0.2.2:8000\nDevice via adb reverse: http://127.0.0.1:8000\nRemote servers require HTTPS.",fontSize=11.sp,modifier=Modifier.padding(top=8.dp)) }
        item { OutlinedTextField(token,{token=it;saved=false},label={Text("Backend access token (not broker token)")},visualTransformation=PasswordVisualTransformation(),singleLine=true,modifier=Modifier.fillMaxWidth()) }
        item { Row(verticalAlignment=Alignment.CenterVertically) { Checkbox(liveMode,{liveMode=it;saved=false});Text("Require real Kite data · disable demo fallback") } }
        item { Button(onClick={ try { require((capital.toDoubleOrNull()?:0.0)>0 && capital.toDouble().isFinite()) { "Enter valid positive capital" }; val r=risk.toDoubleOrNull()?:0.0; require(r>0 && r<=2) { "Risk must be above 0 and no more than 2%" }; vm.repository.baseUrl=url; vm.repository.apiToken=token; vm.repository.requireLive=liveMode; vm.repository.capital=capital; vm.repository.risk=risk;vm.resetConnection();error=null;saved=true } catch(e:Exception) {error=e.message} },modifier=Modifier.fillMaxWidth()) { Text("Save preferences") }; error?.let { Text(it,color=MaterialTheme.colorScheme.error) }; if(saved) Text("Preferences saved",color=MaterialTheme.colorScheme.primary) }
        item { AutomationPanel(vm,server,capital,risk) }
        item { Text("Kite API credentials stay on your server. The phone stores only its backend access token, encrypted using Android Keystore. A hosted HTTPS backend is required for remote use.",fontSize=12.sp) }
        item { Text("Educational tool. Not investment advice. F&O trading involves substantial risk. Backtests do not guarantee future results.",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
