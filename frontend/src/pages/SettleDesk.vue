<script setup>
import { onMounted, ref } from 'vue'
import { getJson, postJson } from '../api'

const runs = ref([])
const err = ref('')
const msg = ref('')
const busy = ref(false)

const proofRunInput = ref('')
const proofRunId = ref(null)
const proofs = ref([])
const proofErr = ref('')

async function load() {
  runs.value = await getJson('/api/settle-runs')
}

async function loadProofs(runId) {
  proofErr.value = ''
  proofs.value = []
  proofRunId.value = null
  if (runId === '' || runId == null) return
  try {
    const rows = await getJson(`/api/settle-runs/${runId}/split-proofs`)
    proofs.value = rows
    proofRunId.value = Number(runId)
  } catch (e) {
    proofErr.value = String(e.message || e)
  }
}

onMounted(async () => {
  try {
    await load()
    if (runs.value.length) {
      proofRunInput.value = runs.value[0].id
      await loadProofs(runs.value[0].id)
    }
  } catch (e) {
    err.value = String(e.message || e)
  }
})

async function runSettle() {
  busy.value = true
  err.value = ''
  msg.value = ''
  try {
    const r = await postJson('/api/settle-runs')
    msg.value = `归并完成 #${r.id}：净额 ${(r.net_cents / 100).toFixed(2)}，已配平冲正 ${(r.applied_reversal_cents / 100).toFixed(2)}，超额隔离 ${(r.excess_quarantine_cents / 100).toFixed(2)}，剩余敞口 ${(r.remaining_exposure_cents / 100).toFixed(2)}`
    await load()
    proofRunInput.value = r.id
    await loadProofs(r.id)
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

function yuan(cents) {
  return (Number(cents || 0) / 100).toFixed(2)
}
</script>

<template>
  <div>
    <h1>归并台</h1>
    <p class="lead">对「待归并」正向与冲正跑一轮净额归并：可配平前缀落余额，超出目标敞口的额度作为超额隔离保留；无原单/账户不符整笔进隔离。</p>
    <p class="note-strip">本轮只处理状态为「待归并」的流水；配平段计入余额，超额隔离段不计入。整轮同事务，失败全部回到操作前。每笔冲正落一条拆笔证明（原冲正键 / applied / excess / 配平前敞口），可按归并运行 id 只读回查。</p>
    <div class="row-actions">
      <button class="btn" :disabled="busy" @click="runSettle">跑净额归并</button>
    </div>
    <p v-if="msg" class="ok">{{ msg }}</p>
    <p v-if="err" class="msg">{{ err }}</p>
    <div class="panel">
      <h2>归并运行</h2>
      <table>
        <thead>
          <tr>
            <th>#</th><th>状态</th><th>正向</th><th>冲正</th><th>已归并</th><th>隔离</th><th>已配平冲正（元）</th><th>超额隔离（元）</th><th>剩余敞口（元）</th><th>净额（元）</th><th>结束</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.status }}</td>
            <td>{{ r.forward_count }}</td>
            <td>{{ r.reversal_count }}</td>
            <td>{{ r.settled_count }}</td>
            <td>{{ r.quarantine_count }}</td>
            <td>{{ yuan(r.applied_reversal_cents) }}</td>
            <td>{{ yuan(r.excess_quarantine_cents) }}</td>
            <td>{{ yuan(r.remaining_exposure_cents) }}</td>
            <td>{{ yuan(r.net_cents) }}</td>
            <td>{{ r.finished_at || '—' }}</td>
          </tr>
          <tr v-if="!runs.length"><td colspan="11">尚无归并运行</td></tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h2>拆笔证明</h2>
      <div class="row-actions">
        <input v-model="proofRunInput" class="input" type="number" min="1" placeholder="归并运行 id" />
        <button class="btn secondary" @click="loadProofs(proofRunInput)">按归并运行查询</button>
      </div>
      <p v-if="proofErr" class="msg">{{ proofErr }}</p>
      <table>
        <thead>
          <tr>
            <th>#</th><th>原冲正键</th><th>账户</th><th>原冲正额（元）</th><th>applied（元）</th><th>excess（元）</th><th>配平前敞口（元）</th><th>等式</th><th>拆分</th><th>隔离行#</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in proofs" :key="p.id">
            <td>{{ p.id }}</td>
            <td>{{ p.parent_entry_key }}</td>
            <td>{{ p.account_code }}</td>
            <td>{{ yuan(p.amount_cents) }}</td>
            <td>{{ yuan(p.applied_cents) }}</td>
            <td>
              <span :class="p.excess_cents > 0 ? 'tag warn' : ''">{{ yuan(p.excess_cents) }}</span>
            </td>
            <td>{{ yuan(p.exposure_before_cents) }}</td>
            <td>
              <span class="tag" :class="p.balanced ? 'on' : 'bad'">
                {{ p.balanced ? 'applied + excess = 原额' : '不成立' }}
              </span>
            </td>
            <td><span class="tag">{{ p.split_kind }}</span></td>
            <td>{{ p.quarantine_item_id ?? '—' }}</td>
          </tr>
          <tr v-if="!proofs.length"><td colspan="10">{{ proofRunId ? '该归并运行无拆笔证明' : '输入归并运行 id 查询' }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

