/**
 * PCC 轉發代理（Google Apps Script Web App）。
 *
 * 為什麼需要：PCC 的 WAF 會封鎖 GitHub Actions 的 IP，但不擋 Google 的 IP。
 * 專案改請這支 GAS 代為抓取 PCC 頁面，再自行解析。
 *
 * 部署：
 *  1. 專案設定 → 指令碼屬性，新增 PROXY_KEY = 一組長隨機字串
 *  2. 部署 → 新增部署 → 類型「網頁應用程式」
 *     執行身分：我；存取權：所有人（靠 PROXY_KEY 擋外人）
 *  3. 把 /exec 網址與 PROXY_KEY 設為專案的 PCC_PROXY_URL、PCC_PROXY_KEY
 *  4. 之後改程式：部署 → 管理部署作業 → 編輯 → 新版本（/exec 網址不變）
 *
 * 呼叫：GET <exec網址>?key=...&url=<編碼後的 PCC 網址>
 * 回傳：JSON {status, body}；代理自身拒絕時為 {status, error}
 */
const ALLOWED_PREFIX = 'https://web.pcc.gov.tw/opas/aspam/public/';

function doGet(e) {
  const p = (e && e.parameter) || {};
  const secret = PropertiesService.getScriptProperties().getProperty('PROXY_KEY');
  if (!secret || p.key !== secret) {
    return json_({ status: 403, error: 'forbidden' });
  }
  const url = p.url || '';
  if (url.indexOf(ALLOWED_PREFIX) !== 0) {
    return json_({ status: 400, error: 'url not allowed' });
  }
  const res = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    followRedirects: true,
  });
  return json_({ status: res.getResponseCode(), body: res.getContentText() });
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
