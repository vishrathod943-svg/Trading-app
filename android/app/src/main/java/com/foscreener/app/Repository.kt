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
    private val cache = java.io.File(context.filesDir, "scan-cache.json")
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
        val builder = Request.Builder().url(baseUrl + path)
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
        withContext(Dispatchers.IO) { cache.writeText(text) }
        return JSONObject(text)
    }
    suspend fun cached(): JSONObject? = withContext(Dispatchers.IO) {
        runCatching { JSONObject(cache.readText()) }.getOrElse {
            runCatching { context.assets.open("scan.json").bufferedReader().use { JSONObject(it.readText()) } }.getOrNull()
        }
    }
    suspend fun bundledDetail(symbol: String): JSONObject? = withContext(Dispatchers.IO) {
        if (!symbol.matches(Regex("[A-Z0-9]+"))) return@withContext null
        runCatching { context.assets.open("stocks/$symbol.json").bufferedReader().use { JSONObject(it.readText()) } }.getOrNull()
    }
    fun live(listener: WebSocketListener): WebSocket = client.newWebSocket(Request.Builder().url(baseUrl.replaceFirst("http", "ws") + "/live").build(), listener)
}
fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
fun JSONObject.money(key: String): String = if (isNull(key)) "—" else "₹%,.2f".format(optDouble(key))
