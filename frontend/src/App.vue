<script setup lang="ts">
import { onMounted, ref } from "vue";
import WeldWorkspace from "./WeldWorkspace.vue";
import { api, setSession, signedIn } from "./session";

const loading = ref(true);
const busy = ref(false);
const password = ref("");
const nextPassword = ref("");
const changing = ref(false);
const error = ref("");

onMounted(async () => {
  try {
    setSession(await api("auth/session"));
  } catch {
    setSession();
  } finally {
    loading.value = false;
  }
});

async function submit(action: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await action();
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : String(failure);
  } finally {
    busy.value = false;
    password.value = "";
    nextPassword.value = "";
  }
}

function login() {
  return submit(async () => setSession(await api("auth/login", { username: "admin", password: password.value })));
}

function logout() {
  return submit(async () => {
    await api("auth/logout", {}, "POST");
    setSession();
    changing.value = false;
  });
}

function changePassword() {
  return submit(async () => {
    await api("auth/password", { current_password: password.value, new_password: nextPassword.value });
    setSession();
    changing.value = false;
  });
}
</script>

<template>
  <main
    v-if="loading"
    aria-busy="true"
  >
    正在检查登录状态
  </main>
  <main
    v-else-if="!signedIn"
    class="auth-panel"
  >
    <h1>管理员登录</h1>
    <form @submit.prevent="login">
      <label>用户名 <input
        value="admin"
        autocomplete="username"
        readonly
      ></label>
      <label>密码 <input
        v-model="password"
        type="password"
        autocomplete="current-password"
        required
      ></label>
      <button :disabled="busy">
        登录
      </button>
    </form>
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
  </main>
  <template v-else>
    <div class="account-bar">
      <span>admin</span>
      <button
        type="button"
        @click="changing = !changing"
      >
        修改密码
      </button>
      <button
        type="button"
        :disabled="busy"
        @click="logout"
      >
        退出登录
      </button>
      <p
        v-if="error"
        role="alert"
      >
        {{ error }}
      </p>
    </div>
    <form
      v-if="changing"
      class="auth-panel"
      @submit.prevent="changePassword"
    >
      <label>当前密码 <input
        v-model="password"
        type="password"
        autocomplete="current-password"
        required
      ></label>
      <label>新密码 <input
        v-model="nextPassword"
        type="password"
        autocomplete="new-password"
        minlength="12"
        required
      ></label>
      <button :disabled="busy">
        保存并重新登录
      </button>
    </form>
    <WeldWorkspace />
  </template>
</template>

<style scoped>
.auth-panel { max-width: 28rem; margin: 3rem auto; padding: 1.5rem; }
.auth-panel form, form.auth-panel { display: grid; gap: 1rem; }
.auth-panel label { display: grid; gap: .25rem; }
.auth-panel input { padding: .5rem; }
.account-bar { display: flex; justify-content: end; align-items: center; gap: .75rem; padding: .5rem 1rem; }
[role="alert"] { color: #9a2323; }
</style>
