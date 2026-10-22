import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { Button } from '@/components/ui/button'

const names: Record<string, string> = { locked: '锁定', equipped: '装备', discarded: '弃置' }
const fields = ['locked', 'equipped', 'discarded']
const choices = (field: string) => [['true', `已${names[field]}`], ['false', `未${names[field]}`]]
type Region = { rect: number[]; mode?: string; templates: Record<string, string> }
type Profile = { client_verified?: boolean; validation?: { expected: Record<string, string> }[] } & Partial<Record<'locked' | 'equipped' | 'discarded', Region>>
type Sample = { id: string; size: number[] }

export default function StateCalibration({ base, busy, onBusy }: { base: string; busy: boolean; onBusy: (value: boolean) => void }) {
    const [profile, setProfile] = useState<Profile>({})
    const [sample, setSample] = useState<Sample | null>(null)
    const [validationSample, setValidationSample] = useState<Sample | null>(null)
    const [field, setField] = useState('locked')
    const [value, setValue] = useState('')
    const [mode, setMode] = useState('glyph')
    const [rect, setRect] = useState<number[] | null>(null)
    const [expected, setExpected] = useState<Record<string, string>>({})
    const [message, setMessage] = useState('')
    const [validationMessage, setValidationMessage] = useState('')
    const [working, setWorking] = useState(false)
    const image = useRef<HTMLImageElement>(null)
    const start = useRef<number[] | null>(null)
    const region = profile[field as keyof Pick<Profile, 'locked' | 'equipped' | 'discarded'>]
    const selected = region?.rect ?? rect
    useEffect(() => { if (base) axios.get(`${base}/review/calibration`).then(r => setProfile(r.data)).catch(() => {}) }, [base])
    const request = async (path: string, data = {}, target: 'template' | 'validation' = 'template') => {
        const forValidation = target === 'validation' || path === 'validate' || path === 'finish'
        if (path === 'validate') {
            const unfilled = Object.keys(names).filter(f => !expected[f])
            if (unfilled.length) {
                setValidationMessage(`请先选择：${unfilled.map(f => names[f]).join('、')}。填写的是截图中各项的真实状态。`)
                return
            }
            setValidationMessage('正在核对截图，请稍候…')
        }
        setWorking(true); onBusy(true)
        if (path === 'capture') {
            const notice = '请在 3 秒内切回游戏，截图完成后再切回来。不会切换或修改遗器。'
            if (forValidation) setValidationMessage(notice)
            else setMessage(notice)
        }
        try {
            const response = await axios.post(`${base}/review/calibration/${path}`, data, { timeout: path === 'capture' ? 60000 : 15000 })
            if (path === 'capture') {
                if (forValidation) {
                    setValidationSample(response.data); setExpected({}); setValidationMessage('验证截图已更新。请填写真实状态，再点击核对。')
                } else {
                    setSample(response.data); setRect(null); setMessage('模板截图已更新。请框选并保存状态模板。')
                }
            }
            else if (path === 'validate') {
                setProfile(response.data.profile)
                setValidationMessage(response.data.errors.length ? '验证未通过：' + response.data.errors.map((e: { field: string; expected: string; actual: string }) => `${names[e.field]}（期望 ${choices(e.field).find(c => c[0] === e.expected)?.[1]}，识别为 ${choices(e.field).find(c => c[0] === e.actual)?.[1] ?? '未知'}）`).join('；') + '。验证覆盖已重置，请检查模板区域。' : '本张独立验证通过。请换另一件遗器继续。')
            } else {
                setProfile(response.data)
                if (path === 'finish') setValidationMessage('本机状态校准已通过。请重新扫描，使结果使用新配置。')
                else {
                    setMessage('模板已保存；修改配置后需要重新独立验证。')
                    setValidationSample(null); setExpected({}); setValidationMessage('模板已更新，请重新截取验证截图。')
                }
            }
        } catch (error) {
            const text = axios.isAxiosError(error) ? (error.code === 'ECONNABORTED' ? '请求超时，请检查后端是否仍在运行。' : String(error.response?.data?.detail ?? error.message)) : String(error)
            if (forValidation) setValidationMessage(text)
            else setMessage(text)
        }
        finally { setWorking(false); onBusy(false) }
    }
    const point = (event: React.PointerEvent) => {
        const bounds = image.current!.getBoundingClientRect()
        return [Math.round(Math.max(0, Math.min(1, (event.clientX-bounds.left)/bounds.width))*sample!.size[0]), Math.round(Math.max(0, Math.min(1, (event.clientY-bounds.top)/bounds.height))*sample!.size[1])]
    }
    const missing = Object.keys(names).flatMap(f => {
        const covered = new Set(profile.validation?.map(c => c.expected[f]))
        const required = ['true', 'false']
        return required.filter(v => !covered.has(v)).map(v => `${names[f]}：${choices(f).find(c => c[0] === v)?.[1]}`)
    })
    const disabled = busy || working
    const templatesReady = fields.every(f => ['true', 'false'].every(v => !!profile[f as 'locked']?.templates[v]))
    return <details className="border rounded p-3">
        <summary className="cursor-pointer font-bold">本机状态校准 · {profile.client_verified ? '已验证' : '未完成'}（点击展开）</summary>
        <div className="flex flex-col gap-3 mt-3">
            <p>全部按五星遗器计算。本机校准仅用于锁定、装备、弃置；词条生效状态沿用自动识别，无需手工校准。用其他遗器验证已保存的状态模板，不限定截图数量。</p>
            <section className="border rounded p-3 flex flex-col gap-3" aria-label="状态模板">
            <h2 className="font-bold">1. 状态模板 · {templatesReady ? '六种状态已保存' : '待填写'}</h2>
            <div className="grid grid-cols-2 gap-2">{fields.flatMap(f => choices(f).map(([v, label]) => <span key={`${f}-${v}`}>{label}：{profile[f as 'locked']?.templates[v] ? '已保存' : '未填写'}</span>))}</div>
            <details>
            <summary className="cursor-pointer">填写 / 修改状态模板（点击展开）</summary>
            <div className="flex flex-col gap-3 mt-3">
            <p>锁定/弃置请紧贴图标框选，使用“白色图形”；装备请选固定状态文字区域，避开角色头像，使用“原色”。同一字段沿用首次框选位置。修改模板会重置独立验证；改变分辨率后需重新校准。</p>
            <Button disabled={!base || disabled} onClick={() => request('capture')}>截取模板截图（3 秒后）</Button>
            <p role="status">{message}</p>
            <div className="flex gap-3 flex-wrap">{fields.map(f => <span key={f}>{names[f]}：{Object.keys(profile[f as 'locked']?.templates ?? {}).map(v => choices(f).find(c => c[0] === v)?.[1]).join('、') || '未设置'}</span>)}</div>
            {sample && <>
                <div className="flex gap-2 flex-wrap items-center">
                    <select aria-label="模板字段" value={field} disabled={disabled} onChange={e => { setField(e.target.value); setValue(''); setRect(null); setMode(['locked', 'discarded'].includes(e.target.value) ? 'glyph' : 'color') }}>{fields.map(f => <option key={f} value={f}>{names[f]}</option>)}</select>
                    <select aria-label="真实状态" value={value} disabled={disabled} onChange={e => setValue(e.target.value)}><option value="">选择真实状态</option>{choices(field).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select>
                    <select aria-label="匹配方式" value={region?.mode ?? mode} disabled={disabled || !!region || field === 'rarity'} onChange={e => setMode(e.target.value)}><option value="glyph">白色图形</option><option value="color">原色</option></select>
                    <Button disabled={disabled || !selected || !value} onClick={() => request('template', { sample_id: sample.id, field, value, rect: selected, mode: region?.mode ?? mode })}>保存此状态模板</Button>
                    <Button variant="outline" disabled={disabled || !region} onClick={() => { setRect(null); request(`reset/${field}`) }}>重置此字段区域</Button>
                </div>
                <p>在下方截图上拖动框选。已有模板的字段会固定框选位置。</p>
                <div className="relative w-full select-none" style={{ touchAction: 'none' }}
                    onPointerDown={e => { if (disabled || region) return; e.currentTarget.setPointerCapture(e.pointerId); start.current = point(e); setRect(null) }}
                    onPointerMove={e => { if (!start.current) return; const p = point(e); setRect([Math.min(p[0], start.current[0]), Math.min(p[1], start.current[1]), Math.abs(p[0]-start.current[0]), Math.abs(p[1]-start.current[1])]) }}
                    onPointerUp={() => { start.current = null }} onPointerCancel={() => { start.current = null }}>
                    <img ref={image} className="w-full" draggable={false} src={`${base}/review/calibration/image/${sample.id}`} alt="校准截图，请框选固定状态区域" />
                    {selected && <div className="absolute border-2 border-red-500 pointer-events-none" style={{ left: `${selected[0]/sample.size[0]*100}%`, top: `${selected[1]/sample.size[1]*100}%`, width: `${selected[2]/sample.size[0]*100}%`, height: `${selected[3]/sample.size[1]*100}%` }} />}
                </div>
            </>}
            </div>
            </details>
            </section>
            <section className="border rounded p-3 flex flex-col gap-3" aria-label="独立验证">
                <h2 className="font-bold">2. 独立验证</h2>
                <p>选择另一件遗器，单独截取验证截图。这里无需框选，也不会修改已保存的模板。</p>
                {!templatesReady && <p>请先保存全部六种状态模板。</p>}
                <Button disabled={!base || disabled || !templatesReady} onClick={() => request('capture', {}, 'validation')}>截取验证截图（3 秒后）</Button>
                {validationSample && <>
                <img className="w-full" src={`${base}/review/calibration/image/${validationSample.id}`} alt="独立验证截图，请填写其中的真实状态" />
                <p>按本区域截图填写锁定、装备、弃置的真实状态。</p>
                <div className="flex gap-3 flex-wrap">{Object.keys(names).map(f => <label key={f}>{names[f]} <select aria-label={`验证${names[f]}`} disabled={disabled} value={expected[f] ?? ''} onChange={e => setExpected({ ...expected, [f]: e.target.value })}><option value="">请选择</option>{choices(f).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>)}</div>
                <Button disabled={disabled} onClick={() => request('validate', { sample_id: validationSample.id, expected })}>{working ? '处理中…' : '核对这张独立截图'}</Button>
            </>}
            <p role="status" aria-live="polite" className="whitespace-pre-wrap">{validationMessage}</p>
            <p>{missing.length ? `尚需验证：${missing.join('；')}` : '所需状态均已验证，可以完成校准。'}</p>
            <Button disabled={disabled || missing.length > 0} onClick={() => request('finish')}>完成状态校准</Button>
            </section>
        </div>
    </details>
}
