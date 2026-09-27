import {
  BriefcaseBusiness,
  Cable,
  History,
  LayoutDashboard,
  Settings2,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  ownerOnly?: boolean;
}

export const navItems: NavItem[] = [
  {
    href: "/",
    label: "Panel",
    description: "Özet, durum ve hızlı tarama",
    icon: LayoutDashboard,
  },
  {
    href: "/jobs",
    label: "İş İlanlarım",
    description: "Eşleşme puanına göre ilanlar",
    icon: BriefcaseBusiness,
  },
  {
    href: "/preferences",
    label: "CV ve Tercihler",
    description: "CV, pozisyon ve çalışma tercihleri",
    icon: Settings2,
  },
  {
    href: "/integrations",
    label: "Entegrasyonlar",
    description: "Gmail, Hotmail/Outlook, Telegram",
    icon: Cable,
  },
  {
    href: "/history",
    label: "Tarama Geçmişi",
    description: "Tarama ve bildirim kayıtları",
    icon: History,
  },
  {
    href: "/team",
    label: "Davetler",
    description: "İkinci kullanıcıyı davet et",
    icon: Users,
    ownerOnly: true,
  },
];
