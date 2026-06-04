{/* 2026-06-01: 设置相关页面 — 通知设置 / 隐私与安全 / 关于与帮助 */}
import { useState, useEffect } from 'react';
import { Bell, BellOff, ChevronLeft, Lock, Shield, Database, Eye, Info, Smartphone, Mail, Activity } from 'lucide-react';
import { Button } from './ui/button';
import { toast } from 'sonner';

// ═══════════════════════════════════════════════════════════
// 通知设置（localStorage 存储）
// ═══════════════════════════════════════════════════════════

interface NotificationSettingsData {
  dailyReminder: boolean;
  medicationReminder: boolean;
  followupReminder: boolean;
  exerciseReminder: boolean;
  reminderTime: string;
}

const DEFAULT_SETTINGS: NotificationSettingsData = {
  dailyReminder: true,
  medicationReminder: true,
  followupReminder: true,
  exerciseReminder: false,
  reminderTime: '09:00',
};

function loadSettings(): NotificationSettingsData {
  try {
    const saved = localStorage.getItem('ortho_notification_settings');
    return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function saveSettings(settings: NotificationSettingsData) {
  localStorage.setItem('ortho_notification_settings', JSON.stringify(settings));
}

export function NotificationSettings({ onBack }: { onBack: () => void }) {
  const [settings, setSettings] = useState<NotificationSettingsData>(loadSettings);

  const toggle = (key: keyof NotificationSettingsData) => {
    if (typeof settings[key] === 'boolean') {
      const updated = { ...settings, [key]: !settings[key] };
      setSettings(updated);
      saveSettings(updated);
      toast.success('设置已保存');
    }
  };

  const items = [
    { key: 'dailyReminder' as const, title: '每日打卡提醒', desc: '每天定时提醒完成康复打卡', icon: Bell },
    { key: 'medicationReminder' as const, title: '用药提醒', desc: '提醒按时服药', icon: Bell },
    { key: 'followupReminder' as const, title: '复诊提醒', desc: '复诊前发送提醒通知', icon: Bell },
    { key: 'exerciseReminder' as const, title: '训练提醒', desc: '提醒完成每日康复训练', icon: Bell },
  ];

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      <div className="bg-white px-4 py-4 flex items-center gap-3 shadow-sm sticky top-0 z-10">
        <button onClick={onBack} className="min-h-[44px] min-w-[44px] flex items-center justify-center">
          <ChevronLeft className="w-6 h-6 text-gray-600" />
        </button>
        <h1 className="font-semibold text-lg">通知设置</h1>
      </div>

      <div className="px-4 pt-6 space-y-4">
        {/* Reminder time */}
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <Bell className="w-5 h-5 text-[#2A79E6]" />
            <div className="flex-1">
              <div className="font-medium text-sm">提醒时间</div>
              <div className="text-xs text-gray-500">每日统一提醒时间</div>
            </div>
          </div>
          <input
            type="time"
            value={settings.reminderTime}
            onChange={(e) => {
              const updated = { ...settings, reminderTime: e.target.value };
              setSettings(updated);
              saveSettings(updated);
            }}
            className="w-full border rounded-xl px-4 py-3 text-sm min-h-[44px]"
          />
        </div>

        {/* Toggle items */}
        <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
          {items.map((item, i) => (
            <div key={item.key}
              className={`flex items-center gap-3 px-5 py-4 ${
                i < items.length - 1 ? 'border-b border-gray-100' : ''
              }`}>
              <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center">
                <item.icon className="w-5 h-5 text-[#2A79E6]" />
              </div>
              <div className="flex-1">
                <div className="font-medium text-sm">{item.title}</div>
                <div className="text-xs text-gray-500">{item.desc}</div>
              </div>
              <button onClick={() => toggle(item.key)}
                className={`w-12 h-6 rounded-full transition-colors ${
                  settings[item.key] ? 'bg-[#48C774]' : 'bg-gray-300'
                }`}>
                <div className={`w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  settings[item.key] ? 'translate-x-6' : 'translate-x-0.5'
                }`} />
              </button>
            </div>
          ))}
        </div>

        <div className="bg-blue-50 rounded-xl p-4">
          <p className="text-xs text-gray-600">
            💡 提示：本应用为本地 Demo，通知功能需浏览器支持。实际推送通知需配合手机 App 或 Service Worker 实现。
          </p>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// 隐私与安全
// ═══════════════════════════════════════════════════════════

export function PrivacySecurity({ onBack }: { onBack: () => void }) {
  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      <div className="bg-white px-4 py-4 flex items-center gap-3 shadow-sm sticky top-0 z-10">
        <button onClick={onBack} className="min-h-[44px] min-w-[44px] flex items-center justify-center">
          <ChevronLeft className="w-6 h-6 text-gray-600" />
        </button>
        <h1 className="font-semibold text-lg">隐私与安全</h1>
      </div>

      <div className="px-4 pt-6 space-y-4">
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-green-50 rounded-full flex items-center justify-center">
              <Shield className="w-5 h-5 text-[#48C774]" />
            </div>
            <div>
              <div className="font-semibold text-sm">数据安全</div>
              <div className="text-xs text-gray-500">您的数据如何被保护</div>
            </div>
          </div>
          <div className="space-y-3 text-sm text-gray-600">
            <div className="flex items-start gap-2">
              <Database className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">本地存储</p>
                <p className="text-xs text-gray-500 mt-0.5">所有患者数据、病历、打卡记录均存储在本地 SQLite 数据库中，不会上传至云端</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Eye className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">AI 对话隐私</p>
                <p className="text-xs text-gray-500 mt-0.5">AI 康复助手通过 Baichuan API 进行推理，对话内容会发送至 AI 服务商。请勿在对话中透露身份证号、银行卡等敏感个人信息</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Lock className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">访问控制</p>
                <p className="text-xs text-gray-500 mt-0.5">当前为本地 Demo 版本，暂无用户登录认证。生产环境建议增加账号密码保护和 HTTPS 加密传输</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h3 className="font-semibold text-sm mb-4">免责声明</h3>
          <div className="space-y-2 text-xs text-gray-500 leading-relaxed">
            <p>1. 本应用为AI辅助工具，所有康复建议仅供参考，不能替代专业医疗诊断和治疗。</p>
            <p>2. 如遇紧急情况（胸痛、呼吸困难、高热不退、伤口大量出血等），请立即拨打120就医。</p>
            <p>3. 用药建议需以主治医生处方为准，本应用提供的用药提醒仅为辅助。</p>
            <p>4. 用户应定期与主治医生沟通康复进展，不应仅依赖AI建议调整康复方案。</p>
          </div>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// 关于与帮助
// ═══════════════════════════════════════════════════════════

export function AboutHelp({ onBack }: { onBack: () => void }) {
  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      <div className="bg-white px-4 py-4 flex items-center gap-3 shadow-sm sticky top-0 z-10">
        <button onClick={onBack} className="min-h-[44px] min-w-[44px] flex items-center justify-center">
          <ChevronLeft className="w-6 h-6 text-gray-600" />
        </button>
        <h1 className="font-semibold text-lg">关于与帮助</h1>
      </div>

      <div className="px-4 pt-6 space-y-4">
        {/* Product Info */}
        <div className="bg-white rounded-2xl p-5 shadow-sm text-center">
          <div className="w-16 h-16 bg-gradient-to-br from-[#2A79E6] to-[#4A90FF] rounded-2xl flex items-center justify-center mx-auto mb-3">
            <Activity className="w-8 h-8 text-white" />
          </div>
          <h2 className="font-bold text-lg mb-1">骨科康复助手</h2>
          <p className="text-sm text-gray-500 mb-2">AI 驱动的个性化术后康复管理</p>
          <div className="inline-block bg-blue-50 text-[#2A79E6] text-xs px-3 py-1 rounded-full font-medium">
            v1.0.0 Demo
          </div>
        </div>

        {/* Features */}
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h3 className="font-semibold text-sm mb-4">主要功能</h3>
          <div className="space-y-3 text-sm text-gray-600">
            <div className="flex items-start gap-2">
              <Activity className="w-4 h-4 text-[#2A79E6] mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">个性化康复计划</p>
                <p className="text-xs text-gray-500 mt-0.5">基于手术类型、术后天数自动生成每日康复方案</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Smartphone className="w-4 h-4 text-[#2A79E6] mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">每日打卡跟踪</p>
                <p className="text-xs text-gray-500 mt-0.5">记录疼痛、活动度、行走能力，追踪康复进度</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Info className="w-4 h-4 text-[#2A79E6] mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">AI 康复管家</p>
                <p className="text-xs text-gray-500 mt-0.5">7×24小时AI助手，解答康复疑问，识别风险信号</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Database className="w-4 h-4 text-[#2A79E6] mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">OCR病历解析</p>
                <p className="text-xs text-gray-500 mt-0.5">上传出院小结/手术记录，AI自动提取关键信息</p>
              </div>
            </div>
          </div>
        </div>

        {/* Help */}
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h3 className="font-semibold text-sm mb-4">使用帮助</h3>
          <div className="space-y-3 text-sm text-gray-600">
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="font-medium text-xs mb-1">📋 如何开始？</p>
              <p className="text-xs text-gray-500">上传出院小结或手动填写手术信息 → 系统自动生成康复计划 → 每天完成打卡和训练</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="font-medium text-xs mb-1">🔄 如何切换患者？</p>
              <p className="text-xs text-gray-500">点击首页右上角「切换患者」或在「我的」页面退出当前档案</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="font-medium text-xs mb-1">📅 复诊计划如何生成？</p>
              <p className="text-xs text-gray-500">进入「复诊计划」页面，点击「AI 生成」即可根据手术类型自动创建标准复诊方案</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-3">
              <p className="font-medium text-xs mb-1">🆘 遇到紧急情况？</p>
              <p className="text-xs text-gray-500 font-medium text-red-500">请立即拨打120急救电话，不要依赖AI判断</p>
            </div>
          </div>
        </div>

        {/* Contact */}
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h3 className="font-semibold text-sm mb-3">技术支持</h3>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <Mail className="w-4 h-4 text-gray-400" />
            <span>联系开发团队获取技术支持</span>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 pb-4">
          © 2026 OrthoRehab AI · Demo Version
        </p>
      </div>
    </div>
  );
}
