<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import type { EChartsOption } from "echarts";
import { ElMessage } from "element-plus";
import Chart from "./Chart.vue";
import { api, request as apiRequest } from "./session";
import { useState } from "./store";
import { display, labels, toMM, toM } from "./units";
/* Dynamic report columns are supplied by the registered scientific artifacts. */
/* eslint-disable @typescript-eslint/no-explicit-any */
const s = useState();
const config = ref<any>();
const overview = ref<any>();
const models = ref<any[]>([]);
const history = ref<any[]>([]);
const output = ref<any>();
const comparison = ref<any>();
const trend = ref<any>();
const task = ref<any>();
const busy = ref(false);
const axis = ref("current_A");
const auxiliary = ref("max_ux_m");
const keys = ["current_A", "voltage_V", "ambient_C", "speed_m_s"] as const;
const steps = ref<Record<string, number>>({
  current_A: 5,
  voltage_V: 0.8,
  ambient_C: 10,
  speed_m_s: 0.0005,
});
const changes = ref<Record<string, number>>({
  current_A: 15,
  voltage_V: 3.2,
  ambient_C: 20,
  speed_m_s: 0.002,
});
const locked = ref<string[]>(["ambient_C"]);
const switchOrder = ref(true);
const report = ref("metrics");
const pages: Record<string, string> = {
  overview: "系统概览",
  predict: "工况预测",
  trend: "参数趋势",
  compare: "顺序比较",
  decision: "工艺参数推荐",
  history: "模型与历史",
};
async function download(kind: string) {
  await safe(async () => {
    const response = await apiRequest("tasks/" + task.value.id + "/exports/" + kind);
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = kind + ".csv";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}
async function safe(fn: () => Promise<void>) {
  busy.value = true;
  try {
    await fn();
  } catch (e) {
    ElMessage.error(String(e));
  } finally {
    busy.value = false;
  }
}
const request = () => ({ model: s.model, current: s.current });
async function refresh() {
  config.value = await api("config?model=" + s.model);
  overview.value = await api("overview");
  history.value = await api("history");
}
async function run() {
  await safe(async () => {
    if (s.page === "predict") output.value = await api("predict", request());
    if (s.page === "compare")
      comparison.value = await api("compare", request());
    if (s.page === "trend")
      trend.value = await api("trend", { ...request(), axis: axis.value });
    await refresh();
  });
}
async function recommend() {
  await safe(async () => {
    const v = await api("tasks", {
      ...request(),
      steps: steps.value,
      max_change: changes.value,
      locked: Object.fromEntries(
        locked.value.map((k) => [k, s.current[k as keyof typeof s.current]]),
      ),
      orders: switchOrder.value ? [1, 2] : [s.current.process_order],
    });
    localStorage.setItem("task", v.id);
    await loadTask(v.id);
  });
}
async function retryTask() {
  await safe(async () => {
    const next = await api("tasks/" + task.value.id + "/retry", {}, "POST");
    localStorage.setItem("task", next.id);
    await loadTask(next.id);
  });
}
async function loadTask(id: string) {
  task.value = await api("tasks/" + id);
}
let timer: ReturnType<typeof setInterval>;
onMounted(() =>
  safe(async () => {
    await refresh();
    models.value = await api("models");
    const id = localStorage.getItem("task");
    if (id) await loadTask(id);
    timer = setInterval(() => {
      if (task.value && ["queued", "running"].includes(task.value.status))
        loadTask(task.value.id).catch(() => {});
    }, 1800);
  }),
);
onBeforeUnmount(() => clearInterval(timer));
const rows = computed(() =>
  output.value
    ? Object.entries(output.value.outputs).map(([key, value]) => ({
        key,
        ...(value as object),
      }))
    : [],
);
function fmt(k: string, v: number) {
  return display(k, v).toPrecision(5);
}
function chart(target: string): EChartsOption {
  const series: any[] = [];
  for (const order of [1, 2]) {
    const data = trend.value.series.filter((r: any) => r.order === order);
    const xs = data.map((r: any) =>
      axis.value === "speed_m_s" ? toMM(r.x) : r.x,
    );
    const val = (r: any, f: string) => display(target, r.outputs[target][f]);
    series.push(
      {
        name: `顺序${order}区间下界`,
        type: "line",
        stack: "band" + order,
        data: data.map((r: any, i: number) => [xs[i], val(r, "lower")]),
        lineStyle: { opacity: 0 },
        symbol: "none",
      },
      {
        name: `顺序${order}95%边际区间`,
        type: "line",
        stack: "band" + order,
        data: data.map((r: any, i: number) => [
          xs[i],
          val(r, "upper") - val(r, "lower"),
        ]),
        areaStyle: { opacity: 0.16 },
        lineStyle: { opacity: 0 },
        symbol: "none",
      },
      {
        name: `模型预测·顺序${order}`,
        type: "line",
        data: data.map((r: any, i: number) => [xs[i], val(r, "prediction")]),
        markLine: {
          symbol: "none",
          data: [
            {
              xAxis:
                axis.value === "speed_m_s"
                  ? toMM(s.current.speed_m_s)
                  : s.current[axis.value as keyof typeof s.current],
              label: { formatter: "当前工况" },
            },
            ...(config.value.limits[target]
              ? [
                  {
                    yAxis: display(target, config.value.limits[target]),
                    label: { formatter: "项目V1上限" },
                  },
                ]
              : []),
          ],
        },
      },
    );
    series.push({
      name: `ANSYS实测仿真·顺序${order}`,
      type: "scatter",
      symbol: "diamond",
      symbolSize: 9,
      data: trend.value.ansys
        .filter((r: any) => r.process_order === order)
        .map((r: any) => [
          axis.value === "speed_m_s" ? toMM(r[axis.value]) : r[axis.value],
          display(target, r[target]),
        ]),
    });
  }
  return {
    title: {
      text: labels[target] + (target.endsWith("_m") ? " (mm)" : " (无量纲)"),
      textStyle: { fontSize: 14 },
    },
    tooltip: { trigger: "axis" },
    legend: { top: 28, type: "scroll" },
    toolbox: { feature: { saveAsImage: { title: "导出图片" } } },
    grid: { top: 85, left: 70, right: 30, bottom: 45 },
    xAxis: { type: "value", name: labels[axis.value], scale: true },
    yAxis: { type: "value", scale: true },
    series,
  };
}
async function review(c: any) {
  await safe(async () => {
    await api(
      "candidates/" + c.id,
      { status: c.review_status, notes: c.notes },
      "PATCH",
    );
    await refresh();
  });
}
</script>
<template>
  <header>
    <b>薄板焊接预测与工艺决策系统</b><span>v0.2 内网部署版 · 冷却约90分钟后的最终结果</span>
  </header>
  <div class="shell">
    <aside>
      <button
        v-for="(label, key) in pages"
        :key="key"
        :class="{ active: s.page === key }"
        @click="s.page = key"
      >
        {{ label }}
      </button>
      <p>固定几何、材料、三点支撑与热源配置</p>
    </aside>
    <main v-loading="busy">
      <h1>{{ pages[s.page] }}</h1>
      <el-alert
        title="项目V1开发目标：位移≤0.10 mm，总应变与塑性应变≤0.030。代理约束满足仍需ANSYS复核，不代表产品验收合格。"
        type="info"
        :closable="false"
      />
      <div
        v-if="!config"
        class="panel"
      >
        正在加载模型配置；加载失败时请检查后端与日志。
      </div>
      <template v-else>
        <section
          v-if="s.page === 'overview' && overview"
          class="panel"
        >
          <h2>真实数据与系统使用</h2>
          <div class="stats">
            <p>
              仿真样本 <strong>{{ overview.samples }}</strong>
            </p>
            <p>
              系统预测 <strong>{{ overview.predictions }}</strong>
            </p>
            <p>
              决策任务 <strong>{{ overview.tasks }}</strong>
            </p>
            <p>
              候选复核：已复核 {{ overview.reviews.reviewed }} / 待复核
              {{ overview.reviews.pending }}
            </p>
          </div>
          <p>
            默认增强模型：{{
              models[0]?.version
            }}。历史测试已参与诊断，指标仅作为开发基准。
          </p>
          <el-button
            type="primary"
            @click="s.page = 'predict'"
          >
            开始工况预测
          </el-button><el-button @click="s.page = 'decision'">
            创建决策任务
          </el-button>
          <h2>核心历史测试指标</h2>
          <el-table
            :data="
              models[0]?.metrics.filter((r: any) =>
                [
                  'max_displacement_m',
                  'total_eqv_strain_max',
                  'plastic_eqv_strain_max',
                ].includes(r.target),
              )
            "
          >
            <el-table-column
              prop="order"
              label="顺序"
            /><el-table-column
              prop="target"
              label="指标 (原始SI单位)"
            /><el-table-column
              prop="mae"
              label="MAE"
            /><el-table-column
              prop="p95"
              label="绝对误差P95"
            />
          </el-table>
        </section>
        <section
          v-if="['predict', 'trend', 'compare', 'decision'].includes(s.page)"
          class="panel"
        >
          <div class="form">
            <label>模型<el-select
              v-model="s.model"
              @change="
                safe(async () => {
                  output = undefined;
                  trend = undefined;
                  comparison = undefined;
                  await refresh();
                })
              "
            ><el-option
              label="增强模型"
              value="enhanced"
            /><el-option
              label="旧基线模型"
              value="baseline"
            /></el-select></label><label
              v-for="k in keys"
              :key="k"
            >{{ labels[k]
            }}<el-input-number
              :model-value="
                k === 'speed_m_s' ? toMM(s.current[k]) : s.current[k]
              "
              :min="config.bounds[k][0] * (k === 'speed_m_s' ? 1000 : 1)"
              :max="config.bounds[k][1] * (k === 'speed_m_s' ? 1000 : 1)"
              :step="k === 'speed_m_s' ? 0.5 : 1"
              @update:model-value="
                (v: number | undefined) => {
                  if (v !== undefined)
                    s.current[k] = k === 'speed_m_s' ? toM(v) : v;
                }
              "
            /></label><label>焊接顺序<el-select v-model="s.current.process_order"><el-option
              :value="1"
              label="1：volume 9 → 7"
            /><el-option
              :value="2"
              label="2：volume 7 → 9"
            /></el-select></label>
          </div>
          <p>
            温度同时联动初温、对流环境温度及参考温度。方向位移只有幅值，各最大值不可相加或合成。
          </p>
          <el-button
            v-if="s.page !== 'decision'"
            type="primary"
            @click="run"
          >
            计算{{ pages[s.page] }}
          </el-button>
        </section>
        <section
          v-if="s.page === 'predict' && output"
          class="panel"
        >
          <p>{{ output.model_version }} / {{ output.tolerance_version }}</p>
          <el-alert
            :title="output.risk"
            :closable="false"
          /><el-table
            :data="rows"
          >
            <el-table-column label="输出">
              <template #default="{ row }">
                {{ labels[row.key] }}
                {{ row.key.endsWith("_m") ? "(mm)" : "(无量纲)" }}
              </template>
            </el-table-column><el-table-column label="预测值">
              <template #default="{ row }">
                {{
                  fmt(row.key, row.prediction)
                }}
              </template>
            </el-table-column><el-table-column label="95%边际预测区间">
              <template #default="{ row }">
                {{ fmt(row.key, row.lower) }} ～
                {{ fmt(row.key, row.upper) }}
              </template>
            </el-table-column><el-table-column label="项目限值 / 保守判断">
              <template #default="{ row }">
                {{
                  row.limit
                    ? fmt(row.key, row.limit) +
                      " / " +
                      (row.feasible ? "代理约束满足" : "超出代理约束")
                    : "辅助指标"
                }}
              </template>
            </el-table-column>
          </el-table>
          <p>区间不是多目标联合保证，也不保证优化点覆盖。</p>
        </section>
        <section
          v-if="s.page === 'trend'"
          class="panel"
        >
          <label>横轴
            <el-select v-model="axis"><el-option
              v-for="k in keys"
              :key="k"
              :value="k"
              :label="labels[k]"
            /></el-select></label><label>辅助输出
            <el-select v-model="auxiliary"><el-option
              v-for="k in [
                'elastic_eqv_strain_max',
                'max_ux_m',
                'max_uy_m',
                'max_uz_m',
              ]"
              :key="k"
              :value="k"
              :label="labels[k]"
            /></el-select></label><template v-if="trend">
            <p>
              {{ trend.match }}；匹配ANSYS点
              {{ trend.ansys.length }} 个。固定参数：{{ trend.fixed }}
            </p>
            <Chart
              v-for="target in [
                'total_eqv_strain_max',
                'plastic_eqv_strain_max',
                'max_displacement_m',
                auxiliary,
              ]"
              :key="target"
              :option="chart(target)"
            />
          </template>
        </section>
        <section
          v-if="s.page === 'compare' && comparison"
          class="panel"
        >
          <p>{{ comparison.note }}</p>
          <el-table
            :data="Object.keys(comparison.differences).map((key) => ({ key }))"
          >
            <el-table-column label="指标">
              <template #default="{ row }">
                {{ labels[row.key] }}
                {{ row.key.endsWith("_m") ? "mm" : "无量纲" }}
              </template>
            </el-table-column><el-table-column
              v-for="(order, i) in comparison.orders"
              :key="i"
              :label="'顺序' + (i + 1) + '：预测 [区间]'"
            >
              <template #default="{ row }">
                {{ fmt(row.key, order.outputs[row.key].prediction) }} [{{
                  fmt(row.key, order.outputs[row.key].lower)
                }}, {{ fmt(row.key, order.outputs[row.key].upper) }}]
                {{
                  order.outputs[row.key].feasible === undefined
                    ? "辅助"
                    : order.outputs[row.key].feasible
                      ? "代理约束满足"
                      : "未满足"
                }}
              </template>
            </el-table-column><el-table-column label="绝对差">
              <template #default="{ row }">
                {{
                  fmt(row.key, comparison.differences[row.key])
                }}
              </template>
            </el-table-column>
          </el-table>
        </section>
        <section
          v-if="s.page === 'decision'"
          class="panel"
        >
          <h2>步长候选搜索</h2>
          <p>
            示例步长为开发设定，尚未确认设备分辨率。不是连续全局最优。速度步长与幅度在此使用
            m/s。
          </p>
          <div class="form">
            <label
              v-for="k in keys"
              :key="k"
            >{{ labels[k] }}<span>步长</span><el-input-number
              v-model="steps[k]"
              :min="0.000001"
              :precision="6"
            /><span>允许调整幅度</span><el-input-number
              v-model="changes[k]"
              :min="0"
              :precision="6"
            /></label>
          </div>
          <el-checkbox-group v-model="locked">
            <el-checkbox
              v-for="k in keys"
              :key="k"
              :value="k"
            >
              锁定{{ labels[k] }}
            </el-checkbox>
          </el-checkbox-group><el-checkbox v-model="switchOrder">
            允许更换顺序
          </el-checkbox><el-button
            type="primary"
            @click="recommend"
          >
            提交搜索任务
          </el-button><template v-if="task">
            <h2>任务 {{ task.id }}</h2>
            <p>
              {{ task.status }} · {{ task.result.message || task.result.error }}
            </p>
            <p>模型 {{ task.model_id }} / 容差 {{ task.tolerance_id }}</p>
            <p v-if="task.result.manifest">
              已评价 {{ task.result.manifest.evaluated }}，代理可行
              {{ task.result.manifest.feasible }}
            </p>
            <el-button
              v-if="['interrupted', 'failed', 'timed_out'].includes(task.status)"
              @click="retryTask"
            >
              重试任务
            </el-button>
            <template v-if="task.status === 'completed'">
              <a
                v-for="kind in [
                  'recommendations',
                  'ansys_verification_queue',
                  'all_candidates',
                ]"
                :key="kind"
                href="#"
                @click.prevent="download(kind)"
              >导出 {{ kind }}　</a><el-table
                :data="task.result.recommendations"
                height="360"
              >
                <el-table-column
                  v-for="key in Object.keys(
                    task.result.recommendations[0] || {},
                  )"
                  :key="key"
                  :prop="key"
                  :label="labels[key] || key"
                  min-width="170"
                />
              </el-table>
              <p>
                导出与候选表采用原始SI单位；_upper 为保守上界。adjustment_cost
                为归一化调整成本。
              </p>
              <div
                v-for="c in task.candidates"
                :key="c.id"
                class="review"
              >
                <span>{{ c.id }}</span><el-select v-model="c.review_status">
                  <el-option
                    value="pending"
                    label="待ANSYS复核"
                  /><el-option
                    value="reviewed"
                    label="已复核（人工登记）"
                  /><el-option
                    value="rejected"
                    label="复核不通过"
                  />
                </el-select><el-input
                  v-model="c.notes"
                  placeholder="ANSYS复核依据和备注"
                /><el-button @click="review(c)">
                  保存复核
                </el-button>
              </div>
            </template>
          </template>
        </section>
        <section
          v-if="s.page === 'history'"
          class="panel"
        >
          <h2>模型证据与数据批次</h2>
          <p>
            历史测试已参与诊断，不是全新独立验收集。内部水平留出为插值压力测试，两端水平留出为边界外推压力测试。表格使用原始SI单位。
          </p>
          <el-radio-group v-model="report">
            <el-radio-button value="metrics">
              历史指标
            </el-radio-button><el-radio-button value="regional">
              区域误差
            </el-radio-button><el-radio-button value="holdout">
              参数水平留出
            </el-radio-button>
          </el-radio-group>
          <div
            v-for="m in models"
            :key="m.key"
          >
            <h3>{{ m.version }}</h3>
            <el-table
              :data="m[report]"
              height="320"
            >
              <el-table-column
                v-for="k in Object.keys(m[report]?.[0] || {})"
                :key="k"
                :prop="k"
                :label="k"
                min-width="170"
              />
            </el-table>
          </div>
          <h2>批次元信息</h2>
          <pre>{{ overview?.batches }}</pre>
          <h2>预测与推荐历史</h2>
          <el-button @click="safe(refresh)">
            刷新历史
          </el-button><el-table :data="history">
            <el-table-column
              prop="created"
              label="时间"
            /><el-table-column
              prop="kind"
              label="类型"
            /><el-table-column
              prop="model_id"
              label="模型"
            /><el-table-column
              prop="tolerance_id"
              label="容差"
            /><el-table-column
              prop="status"
              label="状态"
            /><el-table-column
              label="查看"
            >
              <template #default="{ row }">
                <el-button
                  @click="
                    row.kind === 'decision'
                      ? safe(async () => {
                        await loadTask(row.id);
                        s.page = 'decision';
                      })
                      : ((output = row.result), (s.page = 'predict'))
                  "
                >
                  查看记录
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </template>
    </main>
  </div>
  <footer>
    ANSYS仿真与模型预测以文字及点线形状区分 · 不提供空间云图或产品验收结论
  </footer>
</template>

