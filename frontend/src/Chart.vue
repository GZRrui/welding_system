<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref } from "vue";
import * as echarts from "echarts";
const props = defineProps<{ option: echarts.EChartsOption }>();
const el = ref<HTMLElement>();
let chart: echarts.ECharts | undefined;
const resize = () => chart?.resize();
onMounted(() => {
  chart = echarts.init(el.value!);
  chart.setOption(props.option);
  window.addEventListener("resize", resize);
});
watch(
  () => props.option,
  (v) => chart?.setOption(v, true),
  { deep: true },
);
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});
</script>
<template>
  <div
    ref="el"
    style="height: 330px; width: 100%"
  />
</template>
