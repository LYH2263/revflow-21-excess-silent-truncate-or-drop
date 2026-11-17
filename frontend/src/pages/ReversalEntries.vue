<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJson } from '../api'

const rows = ref([])
const proofsByRun = ref({})
const err = ref('')

onMounted(async () => {
  try {
    rows.value = await getJson('/api/entries?kind=冲正')
    const runs = await getJson('/api/settle-runs')
    const map = {}
    for (const run of runs) {
      const proofs = await getJson(`/api/settle-runs/${run.id}/split-proofs`)
      map[run.id] = Object.fromEntries(proofs.map((p) => [p.parent_entry_key, p]))
    }
    proofsByRun.value = map
  } catch (e) {
    err.value = String(e.message || e)
  }
})

function yuan(cents) {
  return (Number(cents || 0) / 100).toFixed(2)
}

function excess(e) {
  return e.excess_cents ?? 0
}

function proof(e) {
  if (e.settle_run_id == null) return null
  return proofsByRun.value[e.settle_run_id]?.[e.entry_key] ?? null
}

function tagClass(s) {
  return { on: s === '已归并', warn: s === '部分归并', bad: s === '已隔离' }
}

const splitCount = computed(() => rows.value.filter((e) => excess(e) > 0).length)
</script>

<template>
  <div>
    <h1>冲正流水</h1>
    <p class="lead">
      冲正须关联原正向流水键；归并时不超过目标剩余敞口的部分配平计入余额，超出部分作为超额隔离保留，两项共享同一原冲正键。
    </p>
    <p class="note-strip">
      分栏「已配平 / 超额」写入后不可变；超额 &gt; 0 的冲正共 {{ splitCount }} 笔，可在未平隔离页按原冲正键溯源。
      「拆笔证明」列取自归并运行下的证明实体（原冲正键 / applied / excess / 配平前敞口），与分栏同源，不满足 applied + excess = 原额即不入账。
    </p>
    <p v-if="err" class="msg">{{ err }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>流水键</th><th>账户</th><th>冲正金额（元）</th><th>已配平（元）</th><th>超额（元）</th><th>拆分等式</th><th>拆笔证明</th><th>原单键</th><th>业务单</th><th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in rows" :key="e.id">
            <td>{{ e.entry_key }}</td>
            <td>{{ e.account_code }}</td>
            <td>{{ yuan(e.amount_cents) }}</td>
            <td>{{ e.applied_cents == null ? '—' : yuan(e.applied_cents) }}</td>
            <td>
              <span :class="excess(e) > 0 ? 'tag warn' : ''">
                {{ e.excess_cents == null ? '—' : yuan(e.excess_cents) }}
              </span>
            </td>
            <td>
              <template v-if="proof(e)">
                <span class="tag" :class="proof(e).balanced ? 'on' : 'bad'">
                  {{ proof(e).applied_cents }} + {{ proof(e).excess_cents }} = {{ proof(e).amount_cents }}
                </span>
              </template>
              <template v-else>—</template>
            </td>
            <td>
              <template v-if="proof(e)">
                <span class="tag">{{ proof(e).split_kind }}</span>
                <span class="proof-meta">
                  #{{ proof(e).id }} · 配平前敞口 {{ yuan(proof(e).exposure_before_cents) }}
                </span>
              </template>
              <template v-else>—</template>
            </td>
            <td>{{ e.target_entry_key || '—' }}</td>
            <td>{{ e.biz_ref }}</td>
            <td><span class="tag" :class="tagClass(e.status)">{{ e.status }}</span></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="10">尚无冲正流水</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
