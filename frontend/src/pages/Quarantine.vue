<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJson } from '../api'

const rows = ref([])
const proofs = ref({})
const err = ref('')

onMounted(async () => {
  try {
    rows.value = await getJson('/api/quarantine')
    const runs = await getJson('/api/settle-runs')
    const map = {}
    for (const run of runs) {
      const items = await getJson(`/api/settle-runs/${run.id}/split-proofs`)
      for (const p of items) map[p.id] = p
    }
    proofs.value = map
  } catch (e) {
    err.value = String(e.message || e)
  }
})

function yuan(cents) {
  return (Number(cents || 0) / 100).toFixed(2)
}

function isSplit(q) {
  return q.reason === '冲正超额' && (q.split_applied_cents || 0) > 0
}

function proofOf(q) {
  return q.reason === '冲正超额' ? proofs.value[q.id] ?? null : null
}

const splitRows = computed(() => rows.value.filter((q) => q.reason === '冲正超额'))
const excessTotal = computed(() =>
  splitRows.value.reduce((s, q) => s + (q.amount_cents || 0), 0),
)
const appliedTotal = computed(() =>
  splitRows.value.reduce((s, q) => s + (q.split_applied_cents || 0), 0),
)
const proofCount = computed(() => splitRows.value.filter((q) => proofOf(q)).length)
</script>

<template>
  <div>
    <h1>未平隔离</h1>
    <p class="lead">冲正无原单、账户不一致或超出目标剩余敞口的部分，未能配平即在此保留可查。</p>
    <p class="note-strip">
      超额隔离共 {{ splitRows.length }} 行，超额合计 {{ yuan(excessTotal) }}；
      同行可配平前缀合计 {{ yuan(appliedTotal) }}，已计入账户余额。两者共享同一原冲正键。
      其中 {{ proofCount }} 行挂有拆笔证明，证明拉起「原冲正键 / applied / excess / 配平前敞口」，可与冲正分栏逐笔核对。
    </p>
    <p v-if="err" class="msg">{{ err }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>流水键</th><th>账户</th><th>原因</th><th>隔离金额（元）</th><th>其中已配平（元）</th><th>原敞口（元）</th><th>拆分</th><th>拆笔证明</th><th>归并#</th><th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="q in rows" :key="q.id">
            <td>{{ q.entry_key }}</td>
            <td>{{ q.account_code }}</td>
            <td>
              <span class="tag warn">{{ q.reason }}</span>
            </td>
            <td>{{ yuan(q.amount_cents) }}</td>
            <td>{{ isSplit(q) ? yuan(q.split_applied_cents) : '—' }}</td>
            <td>{{ q.reason === '冲正超额' ? yuan(q.exposure_cents) : '—' }}</td>
            <td>
              <span v-if="q.reason === '冲正超额'" class="tag" :class="isSplit(q) ? 'warn' : 'bad'">
                {{ q.split_kind }}
              </span>
              <span v-else>—</span>
            </td>
            <td>
              <template v-if="proofOf(q)">
                <span class="tag" :class="proofOf(q).balanced ? 'on' : 'bad'">
                  #{{ proofOf(q).id }} 等式{{ proofOf(q).balanced ? '成立' : '不成立' }}
                </span>
                <span class="proof-meta">
                  原键 {{ proofOf(q).parent_entry_key }} · 配平 {{ yuan(proofOf(q).applied_cents) }} ·
                  超额 {{ yuan(proofOf(q).excess_cents) }} · 配平前敞口 {{ yuan(proofOf(q).exposure_before_cents) }}
                </span>
              </template>
              <template v-else>—</template>
            </td>
            <td>{{ q.settle_run_id }}</td>
            <td>{{ q.created_at }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="10">暂无隔离项（先跑归并）</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
