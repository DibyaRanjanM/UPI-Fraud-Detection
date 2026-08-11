import { create } from "zustand"

export const useStore = create((set) => ({
  systemMetrics: {},
  analytics: {},
  setSystemMetrics: (data) => set({ systemMetrics: data }),
  setAnalytics: (data) => set({ analytics: data }),
}))