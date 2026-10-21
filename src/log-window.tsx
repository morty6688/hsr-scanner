import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { listen } from '@tauri-apps/api/event'
import './App.css'

function Logs() {
    const [lines, setLines] = useState<string[]>([])
    useEffect(() => {
        let cancelled = false
        const subscriptions = ['backend-log', 'backend-error'].map(event => listen<string>(event, e => {
            if (!cancelled) setLines(lines => [...lines.slice(-499), e.payload])
        }))
        return () => { cancelled = true; subscriptions.forEach(p => p.then(unlisten => unlisten())) }
    }, [])
    return <pre className="p-3 whitespace-pre-wrap text-xs">{lines.join('\n')}</pre>
}
createRoot(document.getElementById('root')!).render(<Logs />)
