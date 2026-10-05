<template>
  <section class="page" data-module="power">
    <header class="page-head">
      <div>
        <h2>供电系统管理</h2>
        <p class="page-desc">维护供电设备：安排修复时录入的运行负荷、绝缘电阻直接落库，列表、详情、运营概览读到的永远是同一份最新读数。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记供电设备</button>
        <button class="btn" type="button" @click="openReport">月度试验报表</button>
        <button class="btn" type="button" @click="exportRows">导出供电系统清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '设备编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="busyKeys.has(actionKey(action, row))"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无供电系统数据，可先登记供电设备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条供电系统记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 修复回执：录入本次负荷、绝缘值，随版本号一起提交落库 -->
    <div v-if="repairTarget" class="modal-mask" @click.self="closeRepair">
      <div class="modal">
        <h3>安排修复 · {{ repairTarget.设备编号 }}</h3>
        <p class="modal-desc">录入修复后的最新读数，落库后列表与详情立即显示本次回执的值。</p>
        <label class="form-item">
          <span>运行负荷 <em>*</em></span>
          <input v-model="repairForm.运行负荷" placeholder="如 820kW" />
        </label>
        <label class="form-item">
          <span>绝缘电阻 <em>*</em></span>
          <input v-model="repairForm.绝缘电阻" placeholder="如 10MΩ" />
        </label>
        <label class="form-item">
          <span>上次试验</span>
          <input v-model="repairForm.上次试验" type="date" />
        </label>
        <p v-if="repairError" class="error-text">{{ repairError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="repairSubmitting" @click="closeRepair">取消</button>
          <button class="btn primary" type="button" :disabled="repairSubmitting" @click="submitRepair">
            {{ repairSubmitting ? '提交中…' : '确认修复并回执' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 详情：单独走 GET /{id}，和列表展示同一份落库数据 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <h3>设备详情 · {{ detail.设备编号 }}</h3>
        <table class="data-table detail-table">
          <tbody>
            <tr v-for="column in columns" :key="column">
              <th>{{ column }}</th>
              <td>{{ detail[column] ?? '—' }}</td>
            </tr>
            <tr><th>读数来源</th><td>{{ detail.读数来源 === '修复录入' ? '修复录入（最新一版）' : '存量记录，沿用原有口径' }}</td></tr>
            <tr><th>数据版本</th><td>{{ detail.version }}</td></tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 月度试验报表 -->
    <div v-if="reportVisible" class="modal-mask wide" @click.self="reportVisible = false">
      <div class="modal wide">
        <h3>供电系统月度试验报表</h3>
        <form class="filter-bar" @submit.prevent="loadReport">
          <label class="filter-item">
            <span>月份</span>
            <input v-model="reportMonth" placeholder="YYYY-MM，默认当月" />
          </label>
          <button class="btn" type="submit">生成报表</button>
        </form>
        <p v-if="reportError" class="error-text">{{ reportError }}</p>
        <template v-if="report">
          <p class="modal-desc">
            {{ report.month }}：本月试验 {{ report.total }} 台（修复录入 {{ report.repaired }} 台、
            按上次试验日期回填存量 {{ report.backfilled_seed }} 台）；
            <span :class="{ 'error-text': report.unfilled_count > 0 }">补不上 {{ report.unfilled_count }} 台</span>
          </p>
          <table class="data-table">
            <thead>
              <tr>
                <th v-for="column in reportColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in report.items" :key="String(item.id)">
                <td v-for="column in reportColumns" :key="column">{{ item[column] ?? '—' }}</td>
              </tr>
              <tr v-if="!report.items.length">
                <td :colspan="reportColumns.length" class="empty-state">本月暂无试验记录</td>
              </tr>
            </tbody>
          </table>
          <template v-if="report.unfilled.length">
            <h4>以下存量记录上次试验日期缺失或无法识别，读数未能回填：</h4>
            <table class="data-table">
              <thead>
                <tr><th>设备编号</th><th>运行负荷（原值）</th><th>绝缘电阻（原值）</th><th>上次试验（原值）</th><th>标注</th></tr>
              </thead>
              <tbody>
                <tr v-for="item in report.unfilled" :key="String(item.id)">
                  <td>{{ item.设备编号 }}</td>
                  <td>{{ item.运行负荷 ?? '—' }}</td>
                  <td>{{ item.绝缘电阻 ?? '—' }}</td>
                  <td>{{ item.上次试验 ?? '—' }}</td>
                  <td class="error-text">{{ item.未回填原因 }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </template>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="reportVisible = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { id: number; version: number }
type DetailRow = Row & {
  读数来源: string
  status: string
}

const ENDPOINT = '/api/power'
const columns = ["设备编号", "设备类型", "电压等级", "所属区域", "运行负荷", "绝缘电阻", "上次试验", "设备状态"]
const actions = ["负荷预警", "绝缘报警", "安排修复"]
const reportColumns = ["设备编号", "设备类型", "运行负荷", "绝缘电阻", "上次试验", "设备状态", "读数来源", "读数备注", "回填方式"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const stats = computed(() => {
  const count = (status: string) => rows.value.filter((row) => row.status === status).length
  return [
    { label: "正常设备", value: count("正常") },
    { label: "负荷过高设备", value: count("负荷过高") },
    { label: "绝缘降低设备", value: count("绝缘降低") },
    { label: "已修复设备", value: count("已修复") },
  ]
})

// 同一行同一动作提交期间禁用按钮，防止双击造成两次请求
const busyKeys = ref<Set<string>>(new Set())
function actionKey(action: string, row: Row) {
  return `${row.id}:${action}`
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '供电设备登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  if (action === '安排修复') {
    openRepair(row)
    return
  }
  errorMessage.value = ''
  const key = actionKey(action, row)
  busyKeys.value.add(key)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, version: row.version } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail || '供电系统动作未生效，请稍后重试')
    }
    // 动作回执即落库后的同一条记录，直接回填本地行；随后再拉列表保持两边一致
    mergeEntry(payload.entry)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '供电系统操作失败'
  } finally {
    busyKeys.value.delete(key)
  }
}

function mergeEntry(entry: Row | null) {
  if (!entry) return
  const index = rows.value.findIndex((row) => row.id === entry.id)
  if (index >= 0) {
    rows.value[index] = entry
  }
}

// ---- 安排修复回执 -------------------------------------------------------

const repairTarget = ref<Row | null>(null)
const repairSubmitting = ref(false)
const repairError = ref('')
const repairForm = reactive({ 运行负荷: '', 绝缘电阻: '', 上次试验: '' })

function openRepair(row: Row) {
  repairTarget.value = row
  repairError.value = ''
  repairForm.运行负荷 = ''
  repairForm.绝缘电阻 = ''
  repairForm.上次试验 = ''
}

function closeRepair() {
  if (repairSubmitting.value) return
  repairTarget.value = null
}

async function submitRepair() {
  const target = repairTarget.value
  if (!target) return
  if (!repairForm.运行负荷.trim() || !repairForm.绝缘电阻.trim()) {
    repairError.value = '运行负荷和绝缘电阻必填，读数不落库不会更新列表'
    return
  }
  repairSubmitting.value = true
  repairError.value = ''
  try {
    // values 是后端统一约定的载荷壳；version 是列表里这行当前版本，用于并发拦截
    const body = {
      values: {
        action: '安排修复',
        version: target.version,
        运行负荷: repairForm.运行负荷.trim(),
        绝缘电阻: repairForm.绝缘电阻.trim(),
        上次试验: repairForm.上次试验,
      },
    }
    const response = await request(`${ENDPOINT}/${target.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => null)
    if (response.status === 409) {
      repairError.value = payload?.detail || '设备数据已被其他修复更新，本次提交未生效'
      await reload()
      const latest = rows.value.find((row) => row.id === target.id)
      if (latest) repairTarget.value = latest
      return
    }
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || payload?.detail || '修复未生效，请稍后重试')
    }
    // 回执里就是落库后的最新读数：先本地回填保证立刻显示，再拉列表对账
    mergeEntry(payload.entry)
    repairTarget.value = null
    await reload()
  } catch (error) {
    repairError.value = error instanceof Error ? error.message : '修复回执提交失败'
  } finally {
    repairSubmitting.value = false
  }
}

// ---- 详情 ---------------------------------------------------------------

const detail = ref<DetailRow | null>(null)

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('设备详情读取失败')
    }
    detail.value = (await response.json()) as DetailRow
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备详情读取失败'
  }
}

// ---- 月度试验报表 -------------------------------------------------------

const reportVisible = ref(false)
const reportMonth = ref('')
const reportError = ref('')

type ReportItem = Row & {
  读数来源: string
  读数备注: string
  回填方式?: string
  未回填原因?: string
}
type Report = {
  month: string
  total: number
  repaired: number
  backfilled_seed: number
  unfilled_count: number
  items: ReportItem[]
  unfilled: ReportItem[]
}
const report = ref<Report | null>(null)

function openReport() {
  reportVisible.value = true
  reportError.value = ''
  if (!report.value) void loadReport()
}

async function loadReport() {
  reportError.value = ''
  const query = reportMonth.value.trim() ? `?month=${encodeURIComponent(reportMonth.value.trim())}` : ''
  try {
    const response = await request(`${ENDPOINT}/monthly-report${query}`)
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(payload?.detail || '月度试验报表生成失败')
    }
    report.value = payload as Report
  } catch (error) {
    reportError.value = error instanceof Error ? error.message : '月度试验报表生成失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('供电设备列表读取失败')
    }
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '供电系统列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  width: 420px;
  max-height: 86vh;
  overflow: auto;
}
.modal.wide { width: 960px; }
.modal h3 { margin: 0 0 6px; font-size: 16px; }
.modal h4 { margin: 14px 0 6px; font-size: 14px; color: #b42318; }
.modal-desc { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
.form-item { display: block; margin-bottom: 10px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item em { color: #b42318; font-style: normal; }
.form-item input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.detail-table th { width: 120px; background: #f8fafc; }
.link:disabled { color: #94a3b8; cursor: not-allowed; }
</style>
