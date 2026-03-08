<template>
  <div style="padding: 20px; font-family: sans-serif;">
    <h1>Web Dashboard</h1>

    <div style="border: 1px solid #ccc; padding: 15px; border-radius: 8px;">
      <h3>Status Komunikasi (REST API) 🔄</h3>
      <p><strong>Pesan dari Backend:</strong> {{ apiMessage }}</p>
    </div>

    <div style="display: flex; gap: 20px; margin-top: 20px;">
      <!-- Placeholder untuk menu-menu dashboard -->
      <button>Modul Inventory</button>
      <button>Modul Transaksi</button>
      <button>Integrasi</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const apiMessage = ref('Memuat dari REST API...')

// Mengambil data dari Backend FastAPI
onMounted(() => {
  fetch('http://localhost:8000/') // URL FastAPI default
    .then(response => response.json())
    .then(data => {
      apiMessage.value = data.message
    })
    .catch(error => {
      apiMessage.value = 'Gagal terhubung ke Backend.'
      console.error(error)
    })
})
</script>

<style scoped>
button {
  padding: 8px 16px;
  cursor: pointer;
}
</style>
