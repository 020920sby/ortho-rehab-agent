import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ── 请求去重：避免短时间内重复提交 ─────────────────

const _pendingRequests = new Map<string, Promise<unknown>>();

/** 去重包装：同一 key 的请求在完成前不会重复发送 */
function dedupe<T>(key: string, factory: () => Promise<T>): Promise<T> {
  const existing = _pendingRequests.get(key);
  if (existing) return existing as Promise<T>;
  const promise = factory().finally(() => {
    _pendingRequests.delete(key);
  });
  _pendingRequests.set(key, promise);
  return promise;
}

// ── 错误格式化 ────────────────────────────────────────

function formatError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    if (err.code === 'ECONNABORTED') return '请求超时，请检查网络后重试';
    if (err.response?.status === 429) return '请求过于频繁，请稍后重试';
    if (err.response?.status === 500) return '服务器异常，请稍后重试';
    if (err.response?.status === 404) return '数据未找到';
    if (!err.response) return '网络连接失败，请检查网络';
    return (err.response?.data as Record<string, unknown>)?.error as string || `请求失败 (${err.response?.status})`;
  }
  return String(err);
}

// ── Types ──────────────────────────────────────────────

export interface PatientInfo {
  patient_id: string;
  name: string;
  age?: number;
  gender?: string;
  surgery_type: string;
  surgery_date: string;
  days_post_op: number;
  recovery_phase: string;
  doctor_name?: string;
  contact?: string;
}

export interface Exercise {
  id: string;
  name: string;
  duration: string;
  sets: string;
  keyPoints: string;
  warning: string;
  completed: boolean;
}

export interface DailyPlan {
  plan_date: string;
  recovery_phase: string;
  daily_goal: string;
  medication: Medication[];
  exercises: PlanExercise[];
  monitoring: Monitoring[];
  precautions: string[];
  next_followup: string;
}

export interface Medication {
  drug_name: string;
  dosage: string;
  frequency: string;
  notes: string;
}

export interface PlanExercise {
  name: string;
  duration: string;
  frequency: string;
  instructions: string;
  caution: string;
}

export interface Monitoring {
  metric: string;
  target: string;
  frequency: string;
}

export interface SafetyResult {
  safety_level: 'normal' | 'attention' | 'warning' | 'emergency';
  reasoning: string;
  recommendation: string;
  requires_doctor_review: boolean;
}

export interface FollowupReport {
  report_id: string;
  summary: string;
  progress_assessment: Record<string, string>;
  key_findings: string[];
  risk_alerts: string[];
  recommendations: string[];
  next_review: string;
}

export interface RehabResponse {
  patient_id: string;
  daily_plan: DailyPlan;
  safety_level: string;
  safety_reasoning: string;
  safety_recommendation: string;
  followup_report: FollowupReport;
}

export interface CheckInData {
  patient_id: string;
  pain_score: number;
  rom: string;
  walking_ability: string;
  symptoms: string[];
  daily_feedback: string;
}

export interface ProgressData {
  pain_trend: { day: string; value: number }[];
  rom_trend: { week: string; value: number; target: number }[];
  milestones: { id: number; title: string; completed: boolean }[];
  daily_records: {
    date: string;
    pain: number;
    rom: number;
    training_complete: boolean;
  }[];
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

// ── Patient ────────────────────────────────────────────

export interface PatientListItem {
  patient_id: string;
  name: string;
  surgery_type: string;
  surgery_date: string;
  days_post_op: number;
  created_at: string;
}

export async function getPatient(patientId: string): Promise<PatientInfo> {
  const { data } = await api.get(`/patient/${patientId}`);
  return data;
}

export async function getPatientHistory(patientId: string) {
  const { data } = await api.get(`/patient/${patientId}/history`);
  return data;
}

export async function listPatients(): Promise<PatientListItem[]> {
  const { data } = await api.get('/patients');
  return data.patients || [];
}

// ── Rehab Plan ─────────────────────────────────────────

export async function generateRehabPlan(patientData: Record<string, unknown>) {
  const { data } = await api.post('/rehab/generate', patientData);
  return data;
}

export async function refreshPlan(patientId: string) {
  const { data } = await api.post('/plan/refresh', { patient_id: patientId });
  return data;
}

export async function submitFeedback(patientId: string, feedback: Record<string, unknown>) {
  const { data } = await api.post(`/rehab/${patientId}/feedback`, feedback);
  return data;
}

// ── AI Chat ────────────────────────────────────────────

export async function chat(messages: ChatMessage[], patientId?: string): Promise<string> {
  const { data } = await api.post('/chat', {
    messages,
    ...(patientId ? { patient_id: patientId } : {}),
  });
  return data.reply;
}

export interface ChatHistoryMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
}

export async function getChatHistory(patientId: string): Promise<ChatHistoryMessage[]> {
  const { data } = await api.get(`/patient/${patientId}/chat/history`);
  return data.messages || [];
}

// ── Exercises ──────────────────────────────────────────

export async function getExercises(patientId: string): Promise<Exercise[]> {
  const { data } = await api.get(`/patient/${patientId}/exercises`);
  return data.exercises;
}

export async function completeExercise(patientId: string, exerciseId: string) {
  const { data } = await api.post(`/patient/${patientId}/exercises/complete`, {
    exercise_id: exerciseId,
  });
  return data;
}

// ── Check-In ───────────────────────────────────────────

export async function submitCheckIn(checkInData: CheckInData) {
  const key = `checkin:${checkInData.patient_id}`;
  return dedupe(key, async () => {
    const { data } = await api.post('/checkin', checkInData);
    return data;
  });
}

// ── Progress ───────────────────────────────────────────

export async function getProgress(patientId: string): Promise<ProgressData> {
  const { data } = await api.get(`/patient/${patientId}/progress`);
  return data;
}

// ── Profile ────────────────────────────────────────────

export async function updatePatient(patientId: string, updates: Record<string, unknown>) {
  const { data } = await api.put(`/patient/${patientId}/profile`, updates);
  return data;
}

// ── Medication ─────────────────────────────────────────

export async function logMedication(patientId: string, payload: {
  drug_name: string;
  taken: boolean;
  dosage?: string;
  skipped_reason?: string;
}) {
  const { data } = await api.post(`/rehab/${patientId}/medication-log`, payload);
  return data;
}

export async function getMedicationLogs(patientId: string) {
  const { data } = await api.get(`/rehab/${patientId}/medication-log`);
  return data;
}

// ── Exercise Log ───────────────────────────────────────

export async function logExercise(patientId: string, payload: {
  exercise_id: string;
  exercise_name?: string;
  completed: boolean;
  skipped_reason?: string;
}) {
  const { data } = await api.post(`/rehab/${patientId}/exercise-log`, payload);
  return data;
}

// ── Medical Orders ─────────────────────────────────────

export async function uploadOrder(file: File, patientId?: string) {
  const formData = new FormData();
  formData.append('file', file);
  if (patientId) formData.append('patient_id', patientId);
  const { data } = await api.post('/order/parse', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export interface OrderRecord {
  id: number;
  patient_id: string;
  filename: string;
  raw_text_preview: string;
  source_type: string;
  created_at: string;
}

export interface OrderDetail extends OrderRecord {
  parsed_data: Record<string, unknown>;
}

export async function getOrderRecords(patientId: string): Promise<OrderRecord[]> {
  const { data } = await api.get(`/patient/${patientId}/orders`);
  return data.orders || [];
}

export async function getOrderDetail(patientId: string, orderId: number): Promise<OrderDetail> {
  const { data } = await api.get(`/patient/${patientId}/orders/${orderId}`);
  return data;
}

// ── Followup Plans ──────────────────────────────────────

export interface FollowupPlan {
  id: number;
  patient_id: string;
  followup_date: string;
  hospital: string;
  department: string;
  doctor_name: string;
  content: string;
  precautions: string;
  materials_to_bring: string;
  reminder_enabled: boolean | number;
  reminder_before_days: number;
  source: string;
  notes: string;
  completed: boolean | number;
  created_at: string;
  updated_at: string;
}

export async function getFollowups(patientId: string, upcomingOnly = false): Promise<{
  followups: FollowupPlan[];
  total: number;
  next_followup: FollowupPlan | null;
}> {
  const { data } = await api.get(`/patient/${patientId}/followups`, {
    params: { upcoming_only: upcomingOnly },
  });
  return data;
}

export async function createFollowup(patientId: string, payload: Partial<FollowupPlan>) {
  const { data } = await api.post(`/patient/${patientId}/followups`, payload);
  return data;
}

export async function updateFollowup(patientId: string, followupId: number, payload: Partial<FollowupPlan>) {
  const { data } = await api.put(`/patient/${patientId}/followups/${followupId}`, payload);
  return data;
}

export async function deleteFollowup(patientId: string, followupId: number) {
  const { data } = await api.delete(`/patient/${patientId}/followups/${followupId}`);
  return data;
}

export async function generateFollowups(patientId: string, surgeryType = '', surgeryDate = '') {
  const { data } = await api.post(`/patient/${patientId}/followups/generate`, {
    surgery_type: surgeryType,
    surgery_date: surgeryDate,
  });
  return data;
}

// ── Emergency Contacts ────────────────────────────────────

export interface EmergencyContact {
  name: string;
  relationship: string;
  phone: string;
}

export async function getEmergencyContacts(patientId: string): Promise<EmergencyContact[]> {
  const { data } = await api.get(`/patient/${patientId}/contacts`);
  return data.contacts || [];
}

export async function saveEmergencyContacts(patientId: string, contacts: EmergencyContact[]) {
  const { data } = await api.put(`/patient/${patientId}/contacts`, { contacts });
  return data;
}

export { formatError };
export default api;
