"use client";

import { useState } from "react";
import EmailViewer from "@/components/mail/EmailViewer";
import MailPage from "@/components/mail/MailPage";

export default function DraftsPage() {
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null);

  const handleEmailSelect = (emailId: string) => {
    setSelectedEmailId(emailId);
  };

  const handleBackToList = () => {
    setSelectedEmailId(null);
  };

  return (
    <div className="flex h-full w-full gap-5">
      <MailPage
        folder="drafts"
        onEmailSelect={handleEmailSelect}
        selectedEmailId={selectedEmailId}
      />
      <div className="flex-1 overflow-y-scroll">
        <EmailViewer emailId={selectedEmailId} onBack={handleBackToList} />
      </div>
    </div>
  );
}
