import { useEffect, useState } from 'react'
import axios from 'axios'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useBackend } from '@/hooks/use-backend'
import { useModal } from '@/hooks/use-modal'
import { getBackendUrl } from '@/lib/utils'
import { toast } from 'sonner'
import { useJsonFile } from '@/apis/files'

type Score = { current_confirmed: boolean; score: number; potential: number; characters: string[] }
type RecordItem = {
    id: string; screenshot: string; ambiguous: boolean; execution: string
    relic: { relic_title?: { title: string; set_name?: string; part?: string }; relic_main_stat?: { name: string; number: string; level: number };
        relic_sub_stat?: { name: string; number: string; activation: string }[] }
    assessment: { decision: 'keep' | 'discard' | 'review'; reasons: string[]; scores: Score[] }
}
type Session = { id: string; status: string; message: string; records: RecordItem[]; counts: Record<string, number> }
const labels = { keep: '保留', discard: '建议弃置', review: '待确认' }
const statuses: Record<string, string> = { scanning: '扫描中', preview: '待预览', executing: '标记中', finished: '已结束', pending: '未执行', success: '成功', skipped: '已跳过', failed: '失败', unverified: '待核验' }

export default function Home() {
    const { backendPort } = useBackend()
    const { onOpen } = useModal()
    const relicSets = useJsonFile('relic/relic_sets.json')
    const titleFor = (title: RecordItem['relic']['relic_title']) => {
        if (!title) return '未知遗器'
        return relicSets.data?.[title.set_name ?? '']?.parts_cn?.[title.part ?? ''] ?? title.title
    }
    const [session, setSession] = useState<Session | null>(null)
    const [threshold, setThreshold] = useState('')
    const [selected, setSelected] = useState<string[]>([])
    const [pending, setPending] = useState(false)
    const base = backendPort ? getBackendUrl(backendPort) : ''
    const busy = pending || session?.status === 'scanning' || session?.status === 'executing'
    useEffect(() => {
        if (!base) return
        let alive = true
        const poll = () => axios.get(`${base}/review`).then(({ data }) => { if (alive) setSession(data) }).catch(() => {})
        axios.get(`${base}/rating-template/init`).catch(() => toast.error('模板初始化失败'))
        poll()
        const timer = setInterval(poll, 1000)
        return () => { alive = false; clearInterval(timer) }
    }, [base])
    const action = async (name: string, data = {}) => {
        setPending(true)
        try {
            const response = await axios.post(`${base}/review/${name}`, data)
            if (name !== 'stop') setSession(response.data)
            setSelected([])
        } catch (error) {
            toast.error(axios.isAxiosError(error) ? String(error.response?.data?.detail ?? error.message) : String(error))
        } finally { setPending(false) }
    }
    return <div className="p-5 flex flex-col gap-4">
        <h1 className="text-xl font-bold">本地遗器清理</h1>
        <p>当前适配每行 8 件：先滚动到列表顶部，选中第一行最左侧遗器。按蛇形逐行扫描，点击开始后有 3 秒切回游戏；Esc 随时停止。</p>
        <div className="flex gap-2 flex-wrap">
            <Button disabled={!base || busy} onClick={() => onOpen('select-template')}>选择模板</Button>
            <Button disabled={!base || busy} onClick={() => action('scan')}>开始扫描（不标记）</Button>
            <Button variant="destructive" disabled={!base} onClick={() => action('stop')}>停止 / 暂停</Button>
        </div>
        <p>四条可见不等于四条生效。未校准生效、锁定、装备和弃置状态时，只生成待确认结果。</p>
        <div className="flex gap-2 items-center">
            <Input className="w-32" type="number" min="1" max="100" placeholder="保留阈值 %" value={threshold} onChange={e => setThreshold(e.target.value)} />
            <Button disabled={busy || !session || !(Number(threshold) > 0 && Number(threshold) <= 100)} onClick={() => action('reprice', { threshold: Number(threshold) / 100 })}>按当前模板重新评分</Button>
        </div>
        <p>状态：{session ? statuses[session.status] ?? session.status : '尚未扫描'} · 已扫描 {session?.records.length ?? 0} 件</p>
        {session?.message && <p role="status">{session.message}</p>}
        {!!session && Object.keys(session.counts).length > 0 && <p>成功 {session.counts.success} / 跳过 {session.counts.skipped} / 失败 {session.counts.failed} / 未执行 {session.counts.unexecuted}</p>}
        <p>执行前请滚动到顶部并选中第一行最左侧，保持每行 8 件、筛选和排序不变；逐件重新核验，不自动强化或分解。</p>
        <Button disabled={busy || session?.status !== 'preview' || !selected.length} onClick={() => action('execute', { session_id: session!.id, selected })}>
            确认标记所选 {selected.length} 件（3 秒后开始）
        </Button>
        {session?.records.map(record => <article key={record.id} className="border rounded p-3 flex gap-4">
            <input aria-label={`选择遗器 ${Number(record.id) + 1}`} type="checkbox" checked={selected.includes(record.id)}
                disabled={busy || record.ambiguous || record.execution !== 'pending' || record.assessment.decision !== 'discard'}
                onChange={e => setSelected(ids => e.target.checked ? [...ids, record.id] : ids.filter(id => id !== record.id))} />
            <a href={`${base}/review/image/${record.screenshot}`} target="_blank" rel="noreferrer"><img className="w-40" alt="扫描截图" src={`${base}/review/image/${record.screenshot}`} /></a>
            <div className="flex flex-col gap-1">
                <b>{titleFor(record.relic.relic_title)} · {labels[record.assessment.decision]}</b>
                <span>{record.relic.relic_main_stat?.name} {record.relic.relic_main_stat?.number} · +{record.relic.relic_main_stat?.level}</span>
                {record.relic.relic_sub_stat?.map(s => <span key={s.name}>{s.name} {s.number} · {{ active: '已生效', pending: '待解锁', unknown: '生效状态未知' }[s.activation] ?? '未知'}</span>)}
                <span>{record.assessment.reasons.join('；')}</span>
                {record.ambiguous && <span>重复内容，禁止自动标记</span>}
                {record.assessment.scores.map((s, i) => <span key={i}>{s.characters.join(' / ')}：当前 {s.current_confirmed ? (s.score * 100).toFixed(1) : '待确认'}，潜力上界 {(s.potential * 100).toFixed(1)}</span>)}
                <span>执行：{statuses[record.execution] ?? record.execution}</span>
            </div>
        </article>)}
    </div>
}
