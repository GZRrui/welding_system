export const display = (key: string, value: number) =>
  key.endsWith("_m") ? value * 1000 : value;
export const toM = (mm: number) => mm / 1000;
export const toMM = (m: number) => m * 1000;
export const labels: Record<string, string> = {
  current_A: "电流 (A)",
  voltage_V: "电压 (V)",
  ambient_C: "联动环境温度 (℃)",
  speed_m_s: "焊速 (mm/s)",
  elastic_eqv_strain_max: "最大等效弹性应变",
  total_eqv_strain_max: "最大等效总应变",
  plastic_eqv_strain_max: "最大等效塑性应变",
  max_displacement_m: "最大总位移幅值",
  max_ux_m: "X位移幅值",
  max_uy_m: "Y位移幅值",
  max_uz_m: "Z位移幅值",
};
