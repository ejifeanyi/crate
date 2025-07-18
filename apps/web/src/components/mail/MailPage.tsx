"use client";

import { useEffect } from "react";
import { useEmailStore } from "@/store/useEmailStore";
import { EmailList } from "@/components/email/EmailList";
import { EmailFolder } from "@/types/email";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface MailPageProps {
  folder: EmailFolder;
  onEmailSelect?: (emailId: string) => void;
  selectedEmailId?: string | null;
}

const MailPage = ({
  folder,
  onEmailSelect,
  selectedEmailId,
}: MailPageProps) => {
  const {
    activeFolder,
    activeCategory,
    setActiveFolder,
    loadEmails,
    emails,
    totalCount,
    page,
    totalPages,
    setPage,
    loading,
    categories,
  } = useEmailStore();

  const unreadCount = emails.filter((email) => !email.isRead).length;

  useEffect(() => {
    if (!activeCategory && activeFolder !== folder) {
      setActiveFolder(folder);
    }

    if (activeCategory || activeFolder !== folder) {
      loadEmails();
    }
  }, [folder, activeFolder, activeCategory, setActiveFolder, loadEmails]);

  const getDisplayTitle = () => {
    if (activeCategory) {
      return activeCategory;
    }

    if (!folder) {
      return "All Mail";
    }

    const titles: Record<Exclude<EmailFolder, null>, string> = {
      inbox: "Inbox",
      favorites: "Favorites",
      sent: "Sent",
      drafts: "Drafts",
      spam: "Spam",
      archive: "Archive",
      trash: "Trash",
    };
    return titles[folder] || folder;
  };

  const getDisplayCounts = () => {
    if (activeCategory) {
      const categoryData = categories.find(
        (cat) => cat.name === activeCategory
      );
      return {
        totalCount: categoryData?.count || emails.length,
        unreadCount: emails.filter((email) => !email.isRead).length,
      };
    }
    return {
      totalCount,
      unreadCount: emails.filter((email) => !email.isRead).length,
    };
  };

  const { totalCount: displayTotalCount, unreadCount: displayUnreadCount } =
    getDisplayCounts();

  const handlePreviousPage = () => {
    if (page > 1) {
      setPage(page - 1);
    }
  };

  const handleNextPage = () => {
    if (page < totalPages) {
      setPage(page + 1);
    }
  };

  const canGoPrevious = page > 1;
  const canGoNext = page < totalPages;

  return (
    <div className="h-full w-130 flex flex-col border border-accent px-6 py-7 rounded-4xl overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold text-accent-foreground">
            {getDisplayTitle()}
          </h1>
          <span className="text-accent-foreground/50 text-xs">
            ({displayTotalCount} Messages, {displayUnreadCount} Unread)
          </span>
        </div>
        <div className="flex items-center justify-end space-x-0.5">
          <span className="text-xs text-accent-foreground/60">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={handlePreviousPage}
            disabled={!canGoPrevious || loading}
            className="h-8 w-8 p-0"
          >
            <ChevronLeft className="h-4 w-4 text-accent-foreground/60" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleNextPage}
            disabled={!canGoNext || loading}
            className="h-8 w-8 p-0"
          >
            <ChevronRight className="h-4 w-4 text-accent-foreground/60" />
          </Button>
        </div>
      </div>
      <EmailList
        onEmailSelect={onEmailSelect}
        selectedEmailId={selectedEmailId}
      />
    </div>
  );
};

export default MailPage;
