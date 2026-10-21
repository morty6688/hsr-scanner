import { useAutoDetectRelicBoxPosition, useUpdateAutoDetectRelicBoxPosition } from '@/apis/config'
import { Switch } from '@/components/ui/switch'
import BoxSetting from './box-setting'

export default function Setting() {
    const detect = useAutoDetectRelicBoxPosition()
    const update = useUpdateAutoDetectRelicBoxPosition()
    return <div className="p-6 flex flex-col gap-6">
        <h1 className="text-xl font-bold">本地扫描设置</h1>
        <p>无在线更新。数据、模型和依赖请按 README 手动维护。</p>
        <label className="flex gap-3 items-center">自动定位遗器区域
            <Switch checked={detect.data ?? true} onCheckedChange={value => update.mutate(value)} />
        </label>
        <p>手动框选使用游戏客户区坐标；改变窗口尺寸或缩放后需重新校准。</p>
        <BoxSetting name="relic_title" />
        <BoxSetting name="relic_main_stat" />
        <BoxSetting name="relic_sub_stat" />
    </div>
}
