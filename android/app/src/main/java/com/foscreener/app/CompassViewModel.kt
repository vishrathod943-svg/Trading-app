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
    val connected: Boolean = false, val message: String? = null
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
            update { it.copy(scan = scan, trades = trades, alerts = alerts, stale = false) }
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
                    update { it.copy(scan = data.getJSONObject("scan"), trades = data.getJSONArray("trades").objects(), alerts = data.getJSONArray("alerts").objects(), stale = false, error = null) }
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
        try { repository.request(path, method, body); update { it.copy(message = "Paper trading updated", error = null) }; refresh() }
        catch (e: Exception) { update { it.copy(error = e.message) } }
    } }
    fun dismissMessage() { update { it.copy(message = null) } }
    override fun onCleared() { generation++; reconnect?.cancel(); socket?.cancel(); super.onCleared() }
}
