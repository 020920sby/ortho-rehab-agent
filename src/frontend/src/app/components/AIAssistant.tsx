import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Input } from './ui/input';
import { Sparkles, Send, AlertTriangle, Lightbulb, MessageSquare, Video, Loader2, RefreshCw, WifiOff, Users, History } from 'lucide-react';
import { usePatient } from '../App';
import { chat, formatError, getChatHistory } from '../../services/api';

interface Message {
  id: number;
  type: 'user' | 'ai' | 'error';
  content: string;
  timestamp: Date;
  canRetry?: boolean;
}

export function AIAssistant() {
  const { patientId, setPatientId, patientName } = usePatient();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      type: 'ai',
      content: '你好！我是你的AI康复管家。我可以帮你解答康复疑问、分析康复进度、提供个性化建议。有什么我可以帮助你的吗？',
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);
  const [lastQuery, setLastQuery] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [showPatientSwitcher, setShowPatientSwitcher] = useState(false);
  const [newPatientId, setNewPatientId] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  // ── 加载聊天历史 ──────────────────────────────

  const loadHistory = useCallback(async () => {
    if (!patientId || patientId === 'default') return;
    try {
      setLoadingHistory(true);
      const history = await getChatHistory(patientId);
      if (history.length > 0) {
        const historyMsgs: Message[] = history.map((h) => ({
          id: h.id,
          type: h.role === 'user' ? 'user' as const : 'ai' as const,
          content: h.content,
          timestamp: new Date(),
        }));
        // 保留欢迎消息 + 追加历史
        setMessages([
          {
            id: 0,
            type: 'ai',
            content: `欢迎回来！我是你的AI康复管家。以下是之前的对话记录。有什么新的问题吗？`,
            timestamp: new Date(),
          },
          ...historyMsgs,
        ]);
      } else {
        // 无历史，显示默认欢迎
        setMessages([
          {
            id: 1,
            type: 'ai',
            content: '你好！我是你的AI康复管家。我可以帮你解答康复疑问、分析康复进度、提供个性化建议。有什么我可以帮助你的吗？',
            timestamp: new Date(),
          },
        ]);
      }
    } catch {
      // 加载失败保持默认消息
    } finally {
      setLoadingHistory(false);
    }
  }, [patientId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // ── 滚动到底部 ────────────────────────────────

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const quickQuestions = [
    { icon: AlertTriangle, text: '膝盖肿了怎么办？', color: 'text-orange-600' },
    { icon: Video, text: '动作不标准如何调整？', color: 'text-blue-600' },
    { icon: Lightbulb, text: '如何加快康复进度？', color: 'text-green-600' },
    { icon: MessageSquare, text: '复诊前需要准备什么？', color: 'text-purple-600' },
  ];

  // ── 患者切换 ──────────────────────────────────

  const handleSwitchPatient = () => {
    const targetId = newPatientId.trim() || patientId;
    if (targetId) {
      setPatientId(targetId);
      setNewPatientId('');
      setShowPatientSwitcher(false);
    }
  };

  const handleSend = async (retryQuery?: string) => {
    const query = retryQuery || inputValue.trim();
    if (!query || sending) return;

    if (!retryQuery) {
      const userMsg: Message = {
        id: messages.length + 1,
        type: 'user',
        content: query,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInputValue('');
      setLastQuery(query);
    }

    setSending(true);

    try {
      const reply = await chat([
        { role: 'user', content: query },
      ], patientId);
      const aiMsg: Message = {
        id: messages.length + 2,
        type: 'ai',
        content: reply,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      const errorText = formatError(err);
      const isNetworkError = errorText.includes('网络') || errorText.includes('连接');

      const errorMsg: Message = {
        id: messages.length + 2,
        type: 'error',
        content: isNetworkError
          ? `⚠️ 网络连接失败\n\n${errorText}\n\n请确认：\n• API 服务已启动（python -m src.api.main）\n• 前端代理配置正确`
          : `⚠️ ${errorText}\n\n请稍后重试，或联系技术支持。`,
        timestamp: new Date(),
        canRetry: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setSending(false);
    }
  };

  const handleRetry = () => {
    // Remove the last error message and retry
    setMessages((prev) => {
      const lastMsg = prev[prev.length - 1];
      if (lastMsg?.canRetry) {
        return prev.slice(0, -1);
      }
      return prev;
    });
    handleSend(lastQuery);
  };

  const handleQuickQuestion = (question: string) => {
    setInputValue(question);
  };

  const isFirstMessage = messages.length <= 1 && messages[0]?.type === 'ai';

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <div className="bg-gradient-to-r from-[#2A79E6] to-[#4A90FF] px-4 py-6 shadow-lg sticky top-0 z-10">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-12 h-12 bg-white/20 rounded-full flex items-center justify-center">
            <Sparkles className="w-7 h-7 text-white" />
          </div>
          <div className="flex-1">
            <h1 className="font-semibold text-xl text-white">AI康复管家</h1>
            <p className="text-sm text-white/90">
              {patientId !== 'default' ? `当前患者：${patientName || patientId}` : '24小时在线 · 专业康复指导'}
            </p>
          </div>
          <button
            onClick={() => setShowPatientSwitcher(!showPatientSwitcher)}
            className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center hover:bg-white/30 transition-colors"
            title="切换患者"
          >
            <Users className="w-5 h-5 text-white" />
          </button>
        </div>

        {/* 患者切换面板 */}
        {showPatientSwitcher && (
          <div className="mt-3 bg-white/15 rounded-xl p-3 backdrop-blur-sm">
            <p className="text-xs text-white/80 mb-2">
              💡 输入新的患者ID即可切换病历。不同患者的问答记录独立保存。
            </p>
            <div className="flex gap-2">
              <Input
                value={newPatientId}
                onChange={(e) => setNewPatientId(e.target.value)}
                placeholder={`当前：${patientId}（输入新ID切换）`}
                className="flex-1 h-9 text-sm bg-white text-gray-800 border-0"
                onKeyDown={(e) => { if (e.key === 'Enter') handleSwitchPatient(); }}
              />
              <Button
                size="sm"
                onClick={handleSwitchPatient}
                className="h-9 bg-white text-[#2A79E6] hover:bg-gray-100"
              >
                切换
              </Button>
            </div>
            <div className="flex gap-2 mt-2">
              {['TKA_test', 'THA_test', 'ACL_test'].map((id) => (
                <button
                  key={id}
                  onClick={() => { setNewPatientId(id); }}
                  className="text-xs text-white/90 bg-white/10 px-2 py-1 rounded hover:bg-white/20"
                >
                  {id}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 px-4 py-4 overflow-y-auto" ref={scrollRef}>
        {/* 加载历史提示 */}
        {loadingHistory && (
          <div className="flex justify-center mb-4">
            <div className="bg-white shadow-sm rounded-full px-4 py-2 flex items-center gap-2">
              <History className="w-4 h-4 text-[#2A79E6] animate-spin" />
              <span className="text-xs text-gray-500">加载历史记录中...</span>
            </div>
          </div>
        )}

        <div className="space-y-4 mb-4">
          {messages.map((message) => (
            <div key={message.id} className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                message.type === 'user'
                  ? 'bg-[#2A79E6] text-white'
                  : message.type === 'error'
                    ? 'bg-red-50 border border-red-200 text-red-800'
                    : 'bg-white shadow-sm text-gray-800'
              }`}>
                {message.type === 'ai' && (
                  <div className="flex items-center gap-2 mb-2">
                    <Sparkles className="w-4 h-4 text-[#2A79E6]" />
                    <span className="text-xs font-medium text-[#2A79E6]">AI康复管家</span>
                  </div>
                )}
                {message.type === 'error' && (
                  <div className="flex items-center gap-2 mb-2">
                    <WifiOff className="w-4 h-4 text-red-500" />
                    <span className="text-xs font-medium text-red-600">连接异常</span>
                  </div>
                )}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
                <div className="flex items-center justify-between mt-2">
                  <p className={`text-xs ${message.type === 'user' ? 'text-white/70' : 'text-gray-400'}`}>
                    {message.timestamp.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                  </p>
                  {message.canRetry && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs h-7 text-red-600 hover:text-red-700 hover:bg-red-100"
                      onClick={handleRetry}
                    >
                      <RefreshCw className="w-3 h-3 mr-1" />重试
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-white shadow-sm rounded-2xl px-4 py-3 flex items-center gap-2">
                <Loader2 className="w-4 h-4 text-[#2A79E6] animate-spin" />
                <span className="text-sm text-gray-500">思考中...</span>
              </div>
            </div>
          )}
        </div>

        {isFirstMessage && (
          <>
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-600 mb-3 px-1">快捷康复提问</h3>
              <div className="grid grid-cols-2 gap-2">
                {quickQuestions.map((question, index) => {
                  const Icon = question.icon;
                  return (
                    <button key={index} onClick={() => handleQuickQuestion(question.text)}
                      className="bg-white rounded-xl p-3 shadow-sm hover:shadow-md transition-shadow text-left min-h-[70px]">
                      <Icon className={`w-5 h-5 ${question.color} mb-2`} />
                      <p className="text-xs text-gray-700">{question.text}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-600 mb-3 px-1">AI专属能力</h3>
              <div className="space-y-2">
                {[
                  { icon: MessageSquare, title: '康复问答', desc: '解答术后康复的各种疑问', color: 'bg-blue-50 text-blue-600' },
                  { icon: AlertTriangle, title: '异常评估', desc: '根据症状评估风险，提供应对建议', color: 'bg-orange-50 text-orange-600' },
                  { icon: Lightbulb, title: '个性化建议', desc: '根据你的打卡数据提供针对性指导', color: 'bg-green-50 text-green-600' },
                  { icon: Video, title: '复诊指导', desc: '告知复诊准备事项和注意事项', color: 'bg-purple-50 text-purple-600' },
                ].map((cap, index) => {
                  const Icon = cap.icon;
                  return (
                    <div key={index}
                      className="w-full bg-white rounded-xl p-4 shadow-sm text-left flex items-center gap-3 min-h-[70px]">
                      <div className={`w-12 h-12 rounded-xl ${cap.color} flex items-center justify-center flex-shrink-0`}>
                        <Icon className="w-6 h-6" />
                      </div>
                      <div className="flex-1">
                        <h4 className="font-medium text-sm mb-1">{cap.title}</h4>
                        <p className="text-xs text-gray-500">{cap.desc}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="bg-white border-t border-gray-200 p-4 pb-20">
        <div className="flex gap-2">
          <Textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="输入您的康复问题..."
            className="flex-1 min-h-[44px] max-h-[120px] resize-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <Button onClick={handleSend} disabled={!inputValue.trim() || sending}
            className="bg-[#2A79E6] hover:bg-[#2267c7] min-w-[44px] min-h-[44px] px-4">
            <Send className="w-5 h-5" />
          </Button>
        </div>
        <p className="text-xs text-gray-400 mt-2 text-center">AI建议仅供参考，如遇紧急情况请立即就医</p>
      </div>
    </div>
  );
}
