<template>
  <section class="page" data-module="power">
    <header class="page-head">
      <div>
        <h2>供电系统管理</h2>
        <p class="page-desc">维护供电设备，围绕设备编号、设备类型、电压等级、所属区域做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记供电设备</button>
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
      <label class="filter-item">
        <span>设备编号</span>
        <input v-model="filters.设备编号" placeholder="按设备编号检索" />
      </label>
      <label class="filter-item">
        <span>设备状态</span>
        <select v-model="filters.设备状态">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="acting"
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
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="report-panel">
      <header class="report-head">
        <h3>月度试验报表</h3>
        <form class="filter-bar" @submit.prevent="loadReport">
          <label class="filter-item">
            <span>报表月份</span>
            <input v-model="reportMonth" type="month" />
          </label>
          <button class="btn" type="submit" :disabled="reportLoading">生成报表</button>
        </form>
      </header>
      <p v-if="reportError" class="error-text">{{ reportError }}</p>
      <template v-if="report">
        <p class="report-meta">
          {{ report.month }} 月试验设备 {{ report.total }} 台；另有 {{ report.unbackfilled_total }} 条存量记录无法回填，已逐条标注（报表生成于 {{ report.generated_at }}）。
        </p>
        <table class="data-table">
          <thead>
            <tr><th v-for="column in columns" :key="column">{{ column }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in report.items" :key="String(item.id)">
              <td v-for="column in columns" :key="column">{{ item[column] ?? '—' }}</td>
            </tr>
            <tr v-if="!report.items.length">
              <td :colspan="columns.length" class="empty-state">该月份没有试验记录</td>
            </tr>
          </tbody>
        </table>
        <template v-if="report.unbackfilled.length">
          <h4 class="report-subhead">无法回填的存量记录</h4>
          <table class="data-table">
            <thead>
              <tr>
                <th v-for="column in columns" :key="column">{{ column }}</th>
                <th>标注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in report.unbackfilled" :key="String(item.id)">
                <td v-for="column in columns" :key="column">{{ item[column] ?? '—' }}</td>
                <td class="mark-text">{{ item.标注 }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </template>
    </section>

    <div v-if="repairTarget" class="dialog-mask" @click.self="closeRepair">
      <form class="dialog" @submit.prevent="submitRepair">
        <h3>安排修复 · {{ repairTarget.设备编号 }}</h3>
        <p class="page-desc">录入本次修复后的读数，确认后直接落库，回执与列表显示同一份数据。</p>
        <label class="filter-item">
          <span>运行负荷</span>
          <input v-model.trim="repairForm.运行负荷" placeholder="如 38A" required />
        </label>
        <label class="filter-item">
          <span>绝缘电阻</span>
          <input v-model.trim="repairForm.绝缘电阻" placeholder="如 1200MΩ" required />
        </label>
        <label class="filter-item">
          <span>试验日期</span>
          <input v-model="repairForm.上次试验" type="date" />
        </label>
        <p v-if="repairError" class="error-text">{{ repairError }}</p>
        <div class="dialog-actions">
          <button class="btn primary" type="submit" :disabled="acting">确认修复</button>
          <button class="btn ghost" type="button" :disabled="acting" @click="closeRepair">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

type MonthlyReport = {
  month: string
  generated_at: string
  items: Row[]
  total: number
  unbackfilled: Row[]
  unbackfilled_total: number
}

const ENDPOINT = '/api/power'
const columns = ["设备编号", "设备类型", "电压等级", "所属区域", "运行负荷", "绝缘电阻", "上次试验", "设备状态"]
const actions = ["负荷预警", "绝缘报警", "安排修复"]
const statuses = ["正常", "负荷过高", "绝缘降低", "已修复"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const acting = ref(false)
const filters = ref<Record<string, string>>({ 设备编号: '', 设备状态: '' })

const stats = computed(() => [
  { label: '正常设备', value: countByStatus('正常') },
  { label: '负荷过高设备', value: countByStatus('负荷过高') },
  { label: '绝缘降低设备', value: countByStatus('绝缘降低') },
])

const repairTarget = ref<Row | null>(null)
const repairForm = ref({ 运行负荷: '', 绝缘电阻: '', 上次试验: '' })
const repairError = ref('')

const reportMonth = ref(new Date().toISOString().slice(0, 7))
const report = ref<MonthlyReport | null>(null)
const reportError = ref('')
const reportLoading = ref(false)

function countByStatus(status: string) {
  return rows.value.filter((row) => row.status === status).length
}

function resetFilters() {
  filters.value = { 设备编号: '', 设备状态: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '供电设备登记入口尚未接入审批流'
}

function runAction(action: string, row: Row) {
  if (action === '安排修复') {
    openRepair(row)
    return
  }
  void submitAction(row, { action })
}

function openRepair(row: Row) {
  repairTarget.value = row
  repairForm.value = {
    运行负荷: String(row.运行负荷 ?? ''),
    绝缘电阻: String(row.绝缘电阻 ?? ''),
    上次试验: new Date().toISOString().slice(0, 10),
  }
  repairError.value = ''
}

function closeRepair() {
  repairTarget.value = null
  repairError.value = ''
}

async function submitRepair() {
  if (!repairTarget.value) {
    return
  }
  const message = await submitAction(repairTarget.value, {
    action: '安排修复',
    运行负荷: repairForm.value.运行负荷,
    绝缘电阻: repairForm.value.绝缘电阻,
    上次试验: repairForm.value.上次试验,
  })
  if (message) {
    repairError.value = message
    return
  }
  closeRepair()
}

async function submitAction(row: Row, values: Record<string, string>): Promise<string> {
  errorMessage.value = ''
  noticeMessage.value = ''
  acting.value = true
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const result = await response.json()
    if (result.entry) {
      mergeRow(result.entry as Row)
    }
    if (!response.ok || !result.ok) {
      return result.message || '供电系统动作未生效，请稍后重试'
    }
    noticeMessage.value = result.message
    await reload()
    return ''
  } catch (error) {
    return error instanceof Error ? error.message : '供电系统操作失败'
  } finally {
    acting.value = false
  }
}

function mergeRow(entry: Row) {
  const index = rows.value.findIndex((row) => String(row.id) === String(entry.id))
  if (index >= 0) {
    rows.value[index] = { ...rows.value[index], ...entry }
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.设备编号) {
    query.set('keyword', filters.value.设备编号)
  }
  if (filters.value.设备状态) {
    query.set('status', filters.value.设备状态)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('供电设备列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '供电系统列表读取失败'
  }
}

async function loadReport() {
  reportError.value = ''
  reportLoading.value = true
  try {
    const query = new URLSearchParams()
    if (reportMonth.value) {
      query.set('month', reportMonth.value)
    }
    const response = await request(`${ENDPOINT}/reports/monthly?${query.toString()}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || '月度试验报表生成失败')
    }
    report.value = payload as MonthlyReport
  } catch (error) {
    report.value = null
    reportError.value = error instanceof Error ? error.message : '月度试验报表生成失败'
  } finally {
    reportLoading.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.notice-text { color: #067647; }
.report-panel { margin-top: 20px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }
.report-head { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; }
.report-head h3 { margin: 0; }
.report-meta { color: var(--muted); font-size: 12px; }
.report-subhead { margin: 16px 0 8px; font-size: 14px; }
.mark-text { color: #b42318; }
.dialog-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; }
.dialog { background: #fff; border-radius: 8px; padding: 20px; width: 360px; display: flex; flex-direction: column; gap: 10px; }
.dialog h3 { margin: 0; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
.link:disabled { color: var(--muted); cursor: not-allowed; }
</style>
