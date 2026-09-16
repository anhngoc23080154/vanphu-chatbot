/**
 * Nội dung tĩnh của landing page, sao chép nguyên văn từ vanphu.vn.
 * Các link đều để "#" vì phạm vi bản clone chỉ là landing page.
 */

export interface NavItem {
  label: string
  href: string
}

export const navItems: NavItem[] = [
  { label: 'Thông tin Văn Phú', href: '#' },
  { label: 'Dự án', href: '#' },
  { label: 'Quan hệ cổ đông', href: '#' },
  { label: 'Phát triển bền vững', href: '#' },
  { label: 'Tin tức', href: '#' },
  { label: 'Liên hệ', href: '#' },
]

export const aboutContent = {
  eyebrow: 'VỀ CHÚNG TÔI',
  titleLine1: 'Thương hiệu',
  titleLine2: 'Bất động sản Vị nhân sinh',
  description:
    'Được dẫn dắt bởi đội ngũ kiến trúc sư tài năng và dạn dày kinh nghiệm, dấu ấn khác biệt của Văn Phú đến từ triết lý kiến tạo không gian sống lấy Con Người làm trọng tâm. Đồng lòng theo đuổi giá trị nhân văn, nghiên cứu toàn diện về nhu cầu sống của con người tại từng cộng đồng, từng địa phương với đa dạng các giá trị văn hóa đặc trưng, Văn Phú kiến tạo nên những dự án vị nhân sinh, góp phần phát triển cộng đồng cư dân văn minh, thịnh vượng và để lại di sản cho thế hệ tương lai.',
}

export interface Stat {
  value: number
  label: string
}

export const stats: Stat[] = [
  { value: 23, label: 'Năm kinh nghiệm' },
  { value: 1905, label: 'Tổng quỹ đất (ha)' },
  { value: 18, label: 'Công ty thành viên' },
]

export const footerIntro =
  'Thành lập từ năm 2003, Công ty Cổ phần Phát triển Bất động sản Văn Phú không chỉ là nhà đầu tư mà còn thể hiện vai trò trong toàn bộ quá trình thực hiện dự án bất động sản: từ khâu nghiên cứu, phát triển, thiết kế, quản lý xây dựng thi công, vận hành và khai thác sau đầu tư. Doanh nghiệp nhanh chóng trở thành một trong những đối tác đáng tin cậy và uy tín trong ngành xây dựng cũng như phát triển dự án. Với nỗ lực Chuyên tâm tạo giá trị sống cùng tầm nhìn tương lai, Văn Phú từng bước khẳng định vị thế trong lĩnh vực bất động sản tại Việt Nam.'

export const contactInfo = [
  {
    icon: 'location' as const,
    text: 'Địa chỉ: Số 104 phố Thái Thịnh, phường Đống Đa, TP Hà Nội, Việt Nam',
    href: '#',
  },
  {
    icon: 'phone' as const,
    text: 'Hotline: (+84) 24 6258 3535',
    href: 'tel:+842462583535',
  },
  {
    icon: 'mail' as const,
    text: 'Email: info@vanphu.vn',
    href: 'mailto:info@vanphu.vn',
  },
]

export const socialLinks: NavItem[] = [
  { label: 'Facebook', href: 'https://www.facebook.com/vanphu.jsc' },
  { label: 'LinkedIn', href: 'https://www.linkedin.com/company/van-phu-jsc/' },
  { label: 'Youtube', href: 'https://www.youtube.com/@vanphujsc' },
]

export const privacyNote = {
  text: 'Công ty chỉ xử lý dữ liệu bạn cung cấp để liên hệ tư vấn sản phẩm, dịch vụ của Công ty. Vui lòng xem',
  linkText:
    'Quy định bảo vệ dữ liệu cá nhân khách hàng, đối tác (gọi chung là "Quy định")',
  href: '#',
}

export const copyright = '© Copyright 2023 by Van Phu. All rights reserved.'
