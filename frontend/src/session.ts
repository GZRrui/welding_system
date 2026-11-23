import { ref } from "vue";
import { ElMessage } from "element-plus";

const csrf = ref("");
export const signedIn = ref(false);

export function setSession(result?: { csrf_token: string }) {
  signedIn.value = Boolean(result);
  csrf.value = result?.csrf_token ?? "";
}

export async function request(path: string, body?: unknown, method?: string) {
  const response = await fetch("/api/v1/" + path, {
    method: method || (body ? "POST" : "GET"),
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf.value,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.ok) return response;
  if (response.status === 401 && signedIn.value) {
    setSession();
    ElMessage.warning("会话已失效，请重新登录");
  }
  const result = await response.json();
  throw Error(typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail));
}

export async function api(path: string, body?: unknown, method?: string) {
  return (await request(path, body, method)).json();
}
