<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常；供电设备读数与供电系统列表、详情同源。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>

    <header class="page-head">
      <div>
        <h3>供电设备最新读数</h3>
        <p class="page-desc">取自设备最后一次落库记录：修复回执提交后，这里与供电系统列表、详情同步更新，修复后的读数只保留最新一版。</p>
      </div>
    </header>
    <table class="data-table">
      <thead>
        <tr><th>设备编号</th><th>运行负荷</th><th>绝缘电阻</th><th>上次试验</th><th>设备状态</th><th>读数来源</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in powerReadings" :key="String(row.id)">
          <td>{{ row.设备编号 ?? '—' }}</td>
          <td>{{ row.运行负荷 ?? '—' }}</td>
          <td>{{ row.绝缘电阻 ?? '—' }}</td>
          <td>{{ row.上次试验 ?? '—' }}</td>
          <td>{{ row.status ?? '—' }}</td>
          <td>{{ row.读数来源 === '修复录入' ? '修复录入（最新一版）' : '存量记录' }}</td>
        </tr>
        <tr v-if="!powerReadings.length">
          <td colspan="6" class="empty-state">暂无供电设备读数</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type PowerReading = {
  id: number
  设备编号: string | null
  运行负荷: string | null
  绝缘电阻: string | null
  上次试验: string | null
  读数来源: string
  status: string
}

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  power_readings?: PowerReading[]
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const powerReadings = ref<PowerReading[]>([])

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    powerReadings.value = payload.power_readings ?? []
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "矿区台账", "created": 0, "pending": 0, "abnormal": 0}, {"name": "瓦斯监测", "created": 0, "pending": 0, "abnormal": 0}, {"name": "通风系统", "created": 0, "pending": 0, "abnormal": 0}, {"name": "顶板管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "水害防治", "created": 0, "pending": 0, "abnormal": 0}, {"name": "冲击地压", "created": 0, "pending": 0, "abnormal": 0}, {"name": "人员定位", "created": 0, "pending": 0, "abnormal": 0}, {"name": "粉尘防治", "created": 0, "pending": 0, "abnormal": 0}, {"name": "防灭火", "created": 0, "pending": 0, "abnormal": 0}, {"name": "皮带运输", "created": 0, "pending": 0, "abnormal": 0}, {"name": "提升系统", "created": 0, "pending": 0, "abnormal": 0}, {"name": "供电系统", "created": 0, "pending": 0, "abnormal": 0}, {"name": "应急救援", "created": 0, "pending": 0, "abnormal": 0}, {"name": "安全培训", "created": 0, "pending": 0, "abnormal": 0}, {"name": "入井管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "爆破管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "巷道维修", "created": 0, "pending": 0, "abnormal": 0}, {"name": "监测分站", "created": 0, "pending": 0, "abnormal": 0}, {"name": "持证管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "应急演练", "created": 0, "pending": 0, "abnormal": 0}]
  }
})
</script>
