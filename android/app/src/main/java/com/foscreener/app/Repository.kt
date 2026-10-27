package com.foscreener.app

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

class Repository(private val context: Context) {
    private val prefs = context.getSharedPreferences("compass", Context.MODE_PRIVATE)
    private val secureToken = SecureToken(context)
    var apiToken: String
        get() = secureToken.read()
        set(value) { secureToken.write(value.trim()) }
    var requireLive: Boolean
        get() = prefs.getBoolean("require_live", false)
        set(value) { prefs.edit { putBoolean("require_live",value) } }
    var demoMarket: String
        get() = prefs.getString("demo_market","US")!!
        set(value) { require(value in listOf("US","India")); prefs.edit { putString("demo_market",value) } }
    private val cache get() = java.io.File(context.filesDir, "scan-${baseUrl.hashCode()}-$requireLive-$demoMarket.json")
    private fun builder(url: String): Request.Builder = Request.Builder().url(url).apply {
        val token = apiToken
        if (token.isNotBlank()) header("Authorization","Bearer $token")
    }
    private val client = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(45, TimeUnit.SECONDS).build()
    var baseUrl: String
        get() = prefs.getString("url", "http://10.0.2.2:8000")!!
        set(value) {
            val uri = java.net.URI(value.trim().trimEnd('/'))
            require(uri.scheme == "https" || (uri.scheme == "http" && uri.host in listOf("10.0.2.2", "127.0.0.1", "localhost"))) { "Use HTTPS, or HTTP on the emulator/loopback only" }
            require(!uri.host.isNullOrBlank() && uri.userInfo == null && uri.rawQuery == null && uri.rawFragment == null) { "Enter a valid backend URL without credentials" }
            prefs.edit { putString("url", value.trim().trimEnd('/')) }
        }
    var capital: String
        get() = prefs.getString("capital", "100000")!!
        set(value) { prefs.edit { putString("capital", value) } }
    var risk: String
        get() = prefs.getString("risk", "1")!!
        set(value) { prefs.edit { putString("risk", value) } }
    var accepted: Boolean
        get() = prefs.getBoolean("accepted", false)
        set(value) { prefs.edit { putBoolean("accepted", value) } }

    suspend fun request(path: String, method: String = "GET", body: JSONObject? = null): String = withContext(Dispatchers.IO) {
        val builder = builder(baseUrl + path)
        if (method == "POST") builder.post((body?.toString() ?: "{}").toRequestBody("application/json".toMediaType()))
        if (method == "DELETE") builder.delete()
        client.newCall(builder.build()).execute().use { response ->
            val text = response.body?.string() ?: throw IOException("Empty response")
            if (!response.isSuccessful) throw IOException(runCatching { JSONObject(text).optString("detail") }.getOrDefault("Request failed (${response.code})"))
            text
        }
    }
    suspend fun scan(): JSONObject {
        val text = request("/scan")
        if (requireLive && JSONObject(text).optString("mode") !in listOf("kite","ibkr")) throw IOException("A live broker backend is required. Demo data cannot satisfy this setting.")
        if (!requireLive && JSONObject(text).optString("mode")=="demo" && demoMarket=="US") throw IOException("This backend serves India demo data. Select India demo or use the US backend.")
        withContext(Dispatchers.IO) { cache.writeText(text) }
        return JSONObject(text)
    }
    suspend fun cached(): JSONObject? = withContext(Dispatchers.IO) {
        runCatching { JSONObject(cache.readText()) }.getOrElse {
            if (requireLive) return@withContext null
            runCatching { context.assets.open(if(demoMarket=="US") "scan-us.json" else "scan.json").bufferedReader().use { JSONObject(it.readText()) } }.getOrNull()
        }
    }
    suspend fun bundledDetail(symbol: String): JSONObject? = withContext(Dispatchers.IO) {
        if (requireLive) return@withContext null
        if (!symbol.matches(Regex("[A-Z0-9]+"))) return@withContext null
        runCatching { context.assets.open(if(demoMarket=="US") "stocks-us/$symbol.json" else "stocks/$symbol.json").bufferedReader().use { JSONObject(it.readText()) } }.getOrNull()
    }
    fun live(listener: WebSocketListener): WebSocket = client.newWebSocket(builder(baseUrl.replaceFirst("http", "ws") + "/live").build(), listener)
}
fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
fun JSONObject.money(key: String, fallbackCurrency: String = "INR"): String {
    if (isNull(key) || !optDouble(key).isFinite()) return "—"
    val sign = if (optString("currency",fallbackCurrency)=="USD") "\$" else "₹"
    return "%s%,.2f".format(java.util.Locale.US,sign,optDouble(key))
}
fun JSONObject.decimal(key: String, digits: Int = 2): String = if (isNull(key) || !optDouble(key).isFinite()) "—" else ("%."+digits+"f").format(java.util.Locale.US,optDouble(key))
