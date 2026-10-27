package com.foscreener.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.Response
import org.json.JSONObject
import org.json.JSONArray

data class CompassState(
    val scan: JSONObject? = null, val detail: JSONObject? = null,
    val trades: List<JSONObject> = emptyList(), val alerts: List<JSONObject> = emptyList(),
    val loading: Boolean = false, val error: String? = null, val stale: Boolean = true,
    val connected: Boolean = false, val message: String? = null,
    val broker: JSONObject? = null, val automation: JSONObject? = null
)
class CompassViewModel(app: Application) : AndroidViewModel(app) {
    val repository = Repository(app)
    private val mutable = MutableStateFlow(CompassState())
    val state = mutable.asStateFlow()
    private var socket: WebSocket? = null
    private var reconnect: kotlinx.coroutines.Job? = null
    private var generation = 0
    init { refresh(); connect() }
    private fun update(block: (CompassState) -> CompassState) { mutable.value = block(mutable.value) }
    fun refresh() { viewModelScope.launch {
        update { it.copy(loading = true, error = null) }
        if (mutable.value.scan == null) {
            val cached = repository.cached()
            update { it.copy(scan = cached, stale = true) }
        }
        try {
            val scan = repository.scan()
            val trades = JSONArray(repository.request("/trades")).objects()
            val alerts = JSONArray(repository.request("/alerts")).objects()
            val broker = JSONObject(repository.request("/broker/status"))
            val automation = JSONObject(repository.request("/automation"))
            update { it.copy(scan = scan, trades = trades, alerts = alerts, stale = scan.optString("mode") in listOf("kite","ibkr") && !broker.optBoolean("ready"),broker=broker,automation=automation) }
        } catch (e: Exception) {
            val cached = repository.cached()
            update { it.copy(scan = it.scan ?: cached, stale = true, error = e.message ?: "Connection failed") }
        } finally { update { it.copy(loading = false) } }
    } }
    fun connect() {
        generation++; val current = generation
        reconnect?.cancel(); socket?.cancel()
        socket = repository.live(object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) { viewModelScope.launch { if (current == generation) update { it.copy(connected = true) } } }
            override fun onMessage(webSocket: WebSocket, text: String) { viewModelScope.launch {
                if (current != generation) return@launch
                runCatching {
                    val data = JSONObject(text)
                    if (repository.requireLive && data.optString("mode") !in listOf("kite","ibkr")) {
                        update { it.copy(scan=null,detail=null,stale=true,error="Live mode requires a broker backend") }
                        return@runCatching
                    }
                    if (data.optString("type")=="ticks") {
                        val quotes=data.getJSONObject("quotes")
                        val old=mutable.value.scan
                        val copy=old?.let { JSONObject(it.toString()) }
                        copy?.optJSONArray("items")?.objects()?.forEach { item ->
                            quotes.optJSONObject(item.optString("exchange")+":"+item.optString("symbol"))?.let { q -> if(!q.isNull("price")) item.put("price",q.optDouble("price")); item.put("tick_age_ms",q.optLong("age_ms")).put("data_type",q.optString("data_type","live")).put("bid",q.opt("bid")).put("ask",q.opt("ask")) }
                        }
                        val d=mutable.value.detail?.let { JSONObject(it.toString()) }
                        d?.let { quotes.optJSONObject(it.optString("exchange")+":"+it.optString("symbol"))?.let { q -> if(!q.isNull("price")) d.put("price",q.optDouble("price")); d.put("tick_age_ms",q.optLong("age_ms")).put("data_type",q.optString("data_type","live")).put("bid",q.opt("bid")).put("ask",q.opt("ask")) } }
                        val broker=data.optJSONObject("broker")
                        update { it.copy(scan=copy,detail=d,broker=broker,stale=broker?.optBoolean("ready")!=true) }
                    } else {
                        val broker=data.optJSONObject("broker")
                        update { it.copy(scan=data.getJSONObject("scan"),trades=data.getJSONArray("trades").objects(),alerts=data.getJSONArray("alerts").objects(),broker=broker,automation=data.optJSONObject("automation"),stale=data.optString("mode") in listOf("kite","ibkr") && broker?.optBoolean("ready")!=true,error=null) }
                    }
                }
            } }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { retry(current) }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { retry(current) }
        })
    }
    private fun retry(current: Int) { viewModelScope.launch {
        if (current != generation) return@launch
        update { it.copy(connected = false, stale = true) }
        reconnect?.cancel()
        reconnect = viewModelScope.launch { delay(10000); if (current == generation) connect() }
    } }
    fun detail(symbol: String) { viewModelScope.launch {
        val bundled = repository.bundledDetail(symbol)
        update { it.copy(detail = bundled, loading = true, error = null) }
        try { val d = JSONObject(repository.request("/stock/$symbol")); update { it.copy(detail = d) } }
        catch (e: Exception) { update { it.copy(error = e.message) } }
        finally { update { it.copy(loading = false) } }
    } }
    fun action(path: String, body: JSONObject? = null, method: String = "POST") { viewModelScope.launch {
        try { repository.request(path, method, body); update { it.copy(message = "Server settings updated", error = null) }; refresh() }
        catch (e: Exception) { update { it.copy(error = e.message) } }
    } }
    fun resetConnection() {
        update { CompassState(loading=true) }
        connect(); refresh()
    }
    fun dismissMessage() { update { it.copy(message = null) } }
    override fun onCleared() { generation++; reconnect?.cancel(); socket?.cancel(); super.onCleared() }
}
