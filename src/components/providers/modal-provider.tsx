import { useEffect, useState } from 'react'
import StartBackendModal from '@/components/modals/start-backend-modal.tsx'
import CreateTemplateModal from '@/components/modals/create-template-modal.tsx'
import { ImportTemplateModal } from '@/components/modals/import-template-modal.tsx'
import SelectTemplateModal from '@/components/modals/select-template-modal.tsx'
import { ExportTemplateModal } from '@/components/modals/export-template-modal.tsx'

export const ModalProvider = () => {
    const [isMounted, setIsMounted] = useState(false)

    useEffect(() => {
        setIsMounted(true)
    }, [])

    if (!isMounted) {
        return null
    }

    return (
        <>
            <StartBackendModal />
            <SelectTemplateModal />
            <CreateTemplateModal />
            <ImportTemplateModal />
            <ExportTemplateModal />
        </>
    )
}
