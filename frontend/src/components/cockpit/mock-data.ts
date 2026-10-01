import type { CityHub, Dossier } from "./types";

export const initialCityDatabase: Record<string, CityHub> = {
      "london": {
            "name": "LONDRA, BİRLEŞİK KRALLIK",
            "lat": 51.5074,
            "lng": -0.1278,
            "count": 6,
            "dossiers": [
                  {
                        "id": "lon-1",
                        "title": "Lead AI Systems & Autonomous Architect",
                        "company": "Synthesia",
                        "location": "London, UK / Global Remote",
                        "salary": "£120,000 - £145,000 + Hisse",
                        "score": "98.4%",
                        "ref": "SYN-LON-01",
                        "freshness": "42 DAKİKA ÖNCE ONAYLANDI",
                        "analysis": "CV'nizdeki Next.js 16 tam yığın mimarisi ve Python/FastAPI ile inşa edilmiş otonom ajan motorları, şirketin yeni nesil video sentezleme platformu için aranan çekirdek liderlik profilini eksiksiz karşılıyor. Londra ofisi veya tamamen uzaktan çalışma izni sunuluyor.",
                        "skills": [
                              "Next.js 16",
                              "Python FastAPI",
                              "Autonomous Agents",
                              "Zero-Latency UI"
                        ],
                        "tier": "Mimari Sistem Lideri",
                        "source": "LinkedIn E-posta Doğrudan Besleme",
                        "telegram": "Kişisel VIP Kanalına 18:24'te iletildi"
                  },
                  {
                        "id": "lon-2",
                        "title": "Staff Machine Learning Infrastructure Lead",
                        "company": "DeepMind Ecosystem",
                        "location": "King's Cross, London",
                        "salary": "£140,000 - £165,000 Taban",
                        "score": "94.6%",
                        "ref": "DPM-LON-02",
                        "freshness": "2 SAAT ÖNCE E-POSTADAN ALINDI",
                        "analysis": "Büyük dil modellerinin dağıtık ölçekte servisi ve mikro-saniye gecikmeli kuyruk yönetimi deneyiminiz bu rol için öncelikli tercih sebebi olarak işaretlendi.",
                        "skills": [
                              "PyTorch",
                              "CUDA Optimization",
                              "vLLM",
                              "Distributed Systems"
                        ],
                        "tier": "Staff Infrastructure",
                        "source": "Resmi ATS Doğrulandı",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "lon-3",
                        "title": "Principal Design Engineer (Craft & Motion)",
                        "company": "Vercel London Hub",
                        "location": "London / Remote",
                        "salary": "£115,000 - £135,000",
                        "score": "91.2%",
                        "ref": "VCL-LON-03",
                        "freshness": "DÜN GECE TARANDI",
                        "analysis": "Emil Kowalski ve Apple Design felsefesine uygun mikro-etkileşimler geliştirme yeteneğiniz, şirketin tasarım sistemleri takımı için doğrudan üst yönetici mülakatı garantiliyor.",
                        "skills": [
                              "Tailwind CSS 4",
                              "React 19",
                              "Motion",
                              "Design Tokens"
                        ],
                        "tier": "Principal Craft Lead",
                        "source": "Greenhouse API",
                        "telegram": "VIP Listeye Eklendi"
                  },
                  {
                        "id": "lon-4",
                        "title": "Senior Distributed Core Backend Architect",
                        "company": "Monzo Tech Hub",
                        "location": "Moorgate, London",
                        "salary": "£110,000 - £130,000 + Hisse",
                        "score": "92.8%",
                        "ref": "MNZ-LON-04",
                        "freshness": "BUGÜN 11:30 TARANDI",
                        "analysis": "Milyonlarca aktif kullanıcılı finansal mikroservisler ve Go/Python mimarileri üzerindeki uzmanlığınız kurumsal mimari direktörü tarafından onaylandı.",
                        "skills": [
                              "Go / Microservices",
                              "Kafka",
                              "PostgreSQL",
                              "Resilience Engineering"
                        ],
                        "tier": "Senior Lead Architect",
                        "source": "Monzo Direct ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "lon-5",
                        "title": "Staff Quantum & AI Algorithmic Lead",
                        "company": "Quantinuum Ecosystem",
                        "location": "Cambridge / London Hub",
                        "salary": "£135,000 - £160,000",
                        "score": "93.4%",
                        "ref": "QNT-LON-05",
                        "freshness": "YENİ TARANDI",
                        "analysis": "Yüksek başarımlı kuantum hesaplama simülasyonları ve hibrit klasik-kuantum optimizasyon algoritmaları alanında araştırma grubu liderliği.",
                        "skills": [
                              "Python C++",
                              "Quantum Sim",
                              "Tensor Networks",
                              "Algorithms"
                        ],
                        "tier": "Staff Research Lead",
                        "source": "Cambridge Talent Feed",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "lon-6",
                        "title": "Principal Cloud Security & Identity Architect",
                        "company": "Revolut Global Hub",
                        "location": "Canary Wharf, London",
                        "salary": "£125,000 - £150,000",
                        "score": "90.8%",
                        "ref": "RVL-LON-06",
                        "freshness": "DÜN AKŞAM",
                        "analysis": "Çok bölgeli sıfır güven (Zero Trust) kimlik doğrulama altyapısı ve küresel API ağ geçidi mimarisi.",
                        "skills": [
                              "OAuth 2.1",
                              "Kubernetes Mesh",
                              "Go",
                              "Cloudflare Zero Trust"
                        ],
                        "tier": "Principal Architect",
                        "source": "Revolut Careers ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "paris": {
            "name": "PARİS, FRANSA",
            "lat": 48.8566,
            "lng": 2.3522,
            "count": 5,
            "dossiers": [
                  {
                        "id": "par-1",
                        "title": "Founding Machine Learning & Agent Partner",
                        "company": "Mistral Ecosystem Partner",
                        "location": "Paris / Hibrit or Remote",
                        "salary": "€130,000 + Kurucu Hissesi",
                        "score": "92.4%",
                        "ref": "MST-PAR-01",
                        "freshness": "RESMİ ATS DOĞRULANDI",
                        "analysis": "Dağıtık LLM çıkarım optimizasyonu ve streaming API konularındaki uzmanlığınız, kurucu ekibin en acil ihtiyacı olan sistem omurgasını tamamlayacak niteliktedir.",
                        "skills": [
                              "Distributed Systems",
                              "vLLM Inference",
                              "Python 3.12",
                              "C++ Core"
                        ],
                        "tier": "Founding Partner / Lead",
                        "source": "Resmi ATS Doğrudan Doğrulama",
                        "telegram": "Kişisel VIP Kanalına 17:15'te iletildi"
                  },
                  {
                        "id": "par-2",
                        "title": "Senior Full-Stack AI Engineer",
                        "company": "Hugging Face Partner",
                        "location": "Paris / Tamamen Uzaktan",
                        "salary": "€110,000 - €125,000",
                        "score": "89.8%",
                        "ref": "HGF-PAR-02",
                        "freshness": "3 SAAT ÖNCE",
                        "analysis": "Açık kaynak model entegrasyonları ve modern Next.js istemci mimarisi yetkinlikleriniz pozisyon için güçlü uyum gösteriyor.",
                        "skills": [
                              "Transformers",
                              "FastAPI",
                              "React",
                              "Docker"
                        ],
                        "tier": "Senior Tier",
                        "source": "Lever ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "par-3",
                        "title": "Staff Cloud Systems Architect",
                        "company": "Datadog Paris Engineering",
                        "location": "Paris / Hybrid",
                        "salary": "€125,000 - €140,000 + RSU",
                        "score": "91.5%",
                        "ref": "DDG-PAR-03",
                        "freshness": "DÜN 19:40",
                        "analysis": "Yüksek hacimli telemetri ve dağıtık gözlemlenebilirlik boru hatlarında mimari liderlik rolü. Çoklu bulut mimarinizle tam eşleşiyor.",
                        "skills": [
                              "Go / Rust",
                              "Kubernetes Core",
                              "OpenTelemetry",
                              "High-Throughput IO"
                        ],
                        "tier": "Staff Cloud Architect",
                        "source": "Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "par-4",
                        "title": "Principal Computer Vision & Multimodal Lead",
                        "company": "Owkin Medical AI",
                        "location": "Paris / Hybrid",
                        "salary": "€115,000 - €135,000",
                        "score": "93.0%",
                        "ref": "OWK-PAR-04",
                        "freshness": "YENİ TARANDI",
                        "analysis": "Federe öğrenme mimarileri ve medikal görüntü işlemede derin sinir ağı optimizasyonu.",
                        "skills": [
                              "PyTorch",
                              "Federated Learning",
                              "Computer Vision",
                              "Medical ML"
                        ],
                        "tier": "Principal Lead",
                        "source": "Lever ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "par-5",
                        "title": "Senior FinTech Security & Cryptography Lead",
                        "company": "Qonto Tech Engineering",
                        "location": "Paris / Remote",
                        "salary": "€105,000 - €120,000",
                        "score": "90.4%",
                        "ref": "QNT-PAR-05",
                        "freshness": "3 SAAT ÖNCE",
                        "analysis": "Avrupa bankacılık regülasyonlarına uygun uçtan uca şifreleme ve mikroservis güvenlik mimarisi.",
                        "skills": [
                              "Go",
                              "Vault",
                              "PCI-DSS",
                              "Security Architecture"
                        ],
                        "tier": "Senior Lead",
                        "source": "Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "sf": {
            "name": "SAN FRANCISCO, ABD",
            "lat": 37.7749,
            "lng": -122.4194,
            "count": 6,
            "dossiers": [
                  {
                        "id": "sf-1",
                        "title": "Principal LLM Agent Architect",
                        "company": "Anthropic Ecosystem Partner",
                        "location": "San Francisco / Global Remote",
                        "salary": "$240,000 - $290,000 Taban + RSU",
                        "score": "95.2%",
                        "ref": "ANT-SF-01",
                        "freshness": "GÜNÜN İLANI",
                        "analysis": "Otonom araç kullanımı, prompt caching ve çok adımlı planlama mimarisi yetkinlikleriniz, Silikon Vadisi merkezli kuruluşun en yüksek kıdem baremine doğrudan uymaktadır.",
                        "skills": [
                              "Claude API",
                              "Python 3.12",
                              "Distributed Queue",
                              "System Design"
                        ],
                        "tier": "Principal Architect",
                        "source": "Ashby ATS Beslemesi",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sf-2",
                        "title": "Staff Design Engineer (Craft & Systems)",
                        "company": "Linear Studio Ecosystem",
                        "location": "San Francisco / Remote",
                        "salary": "$185,000 - $210,000",
                        "score": "90.5%",
                        "ref": "LNR-SF-02",
                        "freshness": "1 GÜN ÖNCE",
                        "analysis": "Sıfır gecikmeli klavye odaklı UI geliştirme ve donanım hızlandırmalı transform bilgisi pozisyonun ana kriterini oluşturuyor.",
                        "skills": [
                              "TypeScript",
                              "Next.js",
                              "Web Animations API",
                              "Tailwind 4"
                        ],
                        "tier": "Staff Design Lead",
                        "source": "Doğrudan Referans Ağı",
                        "telegram": "Kişisel VIP Kanalına Gönderildi"
                  },
                  {
                        "id": "sf-3",
                        "title": "Founding AI Infrastructure Engineer",
                        "company": "OpenAI Ecosystem Partner",
                        "location": "San Francisco / Hybrid",
                        "salary": "$220,000 - $260,000 + Equity",
                        "score": "94.1%",
                        "ref": "OAI-SF-03",
                        "freshness": "4 SAAT ÖNCE",
                        "analysis": "Yüksek hızlı çıkarım sunucuları, tensor paralelizmi ve streaming token boru hatları alanında derin tecrübeniz öncelikli değerlendirmeye alındı.",
                        "skills": [
                              "CUDA",
                              "Triton",
                              "FastAPI",
                              "Distributed LLM"
                        ],
                        "tier": "Founding Infrastructure",
                        "source": "Workday ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sf-4",
                        "title": "Senior Rust Core Systems Architect",
                        "company": "Supabase Ecosystem",
                        "location": "San Francisco / Remote",
                        "salary": "$195,000 - $225,000",
                        "score": "93.0%",
                        "ref": "SUP-SF-04",
                        "freshness": "DÜN GECE",
                        "analysis": "Veritabanı dahili mekanizmaları, sıfır maliyetli soyutlamalar ve PostgreSQL uzantıları geliştirmedeki kanıtlanmış birikiminiz eşleşiyor.",
                        "skills": [
                              "Rust",
                              "PostgreSQL Internals",
                              "Async Runtime",
                              "Wasm"
                        ],
                        "tier": "Staff Systems Lead",
                        "source": "Ashby ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sf-5",
                        "title": "Staff Distributed Data Platform Lead",
                        "company": "Databricks Core Team",
                        "location": "San Francisco / Hybrid",
                        "salary": "$230,000 - $275,000 + RSU",
                        "score": "93.8%",
                        "ref": "DTB-SF-05",
                        "freshness": "2 SAAT ÖNCE",
                        "analysis": "Spark, Delta Lake ve büyük veri işleme altyapılarında yüksek performanslı veri boru hatları liderliği. Dağıtık sistem tasarımıyla tam örtüşüyor.",
                        "skills": [
                              "Apache Spark",
                              "Scala / Python",
                              "Delta Engine",
                              "Distributed Storage"
                        ],
                        "tier": "Staff Platform Lead",
                        "source": "Databricks Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sf-6",
                        "title": "Principal Autonomous AI Evaluation Lead",
                        "company": "Scale AI Engineering",
                        "location": "San Francisco / Remote",
                        "salary": "$210,000 - $250,000",
                        "score": "91.7%",
                        "ref": "SCL-SF-06",
                        "freshness": "BUGÜN 13:45",
                        "analysis": "Çok adımlı ajanların doğruluk ve güvenlik kıyaslamaları (benchmarks) ile RLHF boru hatları geliştirme pozisyonu.",
                        "skills": [
                              "LLM Eval",
                              "Python",
                              "RLHF Workflows",
                              "API Design"
                        ],
                        "tier": "Principal Research Lead",
                        "source": "Lever ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "newyork": {
            "name": "NEW YORK, ABD",
            "lat": 40.7128,
            "lng": -74.006,
            "count": 6,
            "dossiers": [
                  {
                        "id": "ny-1",
                        "title": "Head of Quantitative AI Engineering",
                        "company": "Two Sigma Tech Hub",
                        "location": "Manhattan, New York",
                        "salary": "$260,000 - $320,000 Taban + Bonus",
                        "score": "96.7%",
                        "ref": "TSG-NY-01",
                        "freshness": "YENİ DOĞRULANDI",
                        "analysis": "Mikrosaniye gecikmeli emir iletimi, asenkron veri işleme ve karmaşık algoritmik modelleme uzmanlığınız Wall Street standartlarında en yüksek skoru aldı.",
                        "skills": [
                              "Python C++ Hybrid",
                              "High-Frequency Data",
                              "AsyncIO",
                              "Zero-Copy Mem"
                        ],
                        "tier": "Head of Engineering",
                        "source": "Wall Street ATS Private",
                        "telegram": "VIP Kanalına 09:12'de iletildi"
                  },
                  {
                        "id": "ny-2",
                        "title": "Staff Full-Stack Systems Lead",
                        "company": "Bloomberg Core AI",
                        "location": "New York / Hybrid",
                        "salary": "$210,000 - $250,000",
                        "score": "93.4%",
                        "ref": "BLM-NY-02",
                        "freshness": "3 SAAT ÖNCE",
                        "analysis": "Yüksek yoğunluklu finansal terminaller için modern reaktif arayüz mimarisi ve mikro-önuç tasarımı.",
                        "skills": [
                              "TypeScript",
                              "React 19",
                              "C++ Engine",
                              "WebSockets"
                        ],
                        "tier": "Staff Lead",
                        "source": "Bloomberg Careers ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ny-3",
                        "title": "Principal Financial ML Architect",
                        "company": "Jane Street Partner",
                        "location": "New York / On-site",
                        "salary": "$280,000 - $340,000 Toplam Paket",
                        "score": "92.2%",
                        "ref": "JST-NY-03",
                        "freshness": "BUGÜN TARANDI",
                        "analysis": "Yüksek hacimli zaman serisi tahminleme modelleri ve ölçeklenebilir çıkarım altyapısı.",
                        "skills": [
                              "Python 3.12",
                              "Distributed Train",
                              "PyTorch",
                              "Kubernetes"
                        ],
                        "tier": "Principal Tier",
                        "source": "Lever ATS Beslemesi",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ny-4",
                        "title": "Senior Ultra-Low-Latency Trading Architect",
                        "company": "Hudson River Trading Ecosystem",
                        "location": "Manhattan, New York",
                        "salary": "$270,000 - $330,000",
                        "score": "95.1%",
                        "ref": "HRT-NY-04",
                        "freshness": "4 SAAT ÖNCE",
                        "analysis": "Mikrosaniye altı haberleşme katmanları, FPGA-CPU veri köprüleri ve çekirdek seviyesi optimizasyon.",
                        "skills": [
                              "C++20",
                              "Kernel Bypass",
                              "Low-Latency Networking",
                              "Linux"
                        ],
                        "tier": "Principal Systems Engineer",
                        "source": "Wall Street Direct ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ny-5",
                        "title": "Staff Generative Media & Visuals Lead",
                        "company": "Runway AI Hub",
                        "location": "New York / Remote",
                        "salary": "$215,000 - $255,000 + Equity",
                        "score": "92.3%",
                        "ref": "RNW-NY-05",
                        "freshness": "BUGÜN TARANDI",
                        "analysis": "Yeni nesil üretken video ve difüzyon modellerinin ölçekli çıkarımı ve gerçek zamanlı streaming boru hatları.",
                        "skills": [
                              "Diffusion Models",
                              "PyTorch",
                              "WebGL / WebGPU",
                              "Python"
                        ],
                        "tier": "Staff Creative Technologist",
                        "source": "Ashby ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ny-6",
                        "title": "Principal Data Infrastructure Engineer",
                        "company": "MongoDB Core Architecture",
                        "location": "New York / Hybrid",
                        "salary": "$200,000 - $240,000",
                        "score": "91.0%",
                        "ref": "MDB-NY-06",
                        "freshness": "DÜN GECE",
                        "analysis": "Dağıtık doküman veri motorunda küme koordinasyonu, asenkron replikasyon ve depolama motoru optimizasyonu.",
                        "skills": [
                              "C++",
                              "Distributed Consensus",
                              "Raft",
                              "Database Internals"
                        ],
                        "tier": "Principal Engineer",
                        "source": "Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "amsterdam": {
            "name": "AMSTERDAM, HOLLANDA",
            "lat": 52.3676,
            "lng": 4.9041,
            "count": 5,
            "dossiers": [
                  {
                        "id": "ams-1",
                        "title": "Staff Platform & Distributed Systems Lead",
                        "company": "Adyen Global Hub",
                        "location": "Amsterdam / Hybrid",
                        "salary": "€135,000 - €155,000 + Hisse",
                        "score": "94.8%",
                        "ref": "ADY-AMS-01",
                        "freshness": "ÖNCELİKLİ DOĞRULAMA",
                        "analysis": "Küresel ödeme ağlarında sıfır kesinti, çok bölgeli aktif-aktif kümeleme ve dayanıklı kuyruk yönetimi liderliği.",
                        "skills": [
                              "Java Core",
                              "Python",
                              "High-Availability DB",
                              "Kafka Streams"
                        ],
                        "tier": "Staff Platform Lead",
                        "source": "Adyen ATS Direct",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ams-2",
                        "title": "Principal Frontend Architect",
                        "company": "Booking.com Core",
                        "location": "Amsterdam / Hybrid",
                        "salary": "€120,000 - €140,000",
                        "score": "91.9%",
                        "ref": "BKG-AMS-02",
                        "freshness": "5 SAAT ÖNCE",
                        "analysis": "Milyonlarca eşzamanlı oturumda mikro-önuç ayrışımı ve Core Web Vitals optimizasyonu.",
                        "skills": [
                              "Next.js",
                              "Edge Caching",
                              "Tailwind CSS",
                              "Architecture"
                        ],
                        "tier": "Principal Architect",
                        "source": "SmartRecruiters ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ams-3",
                        "title": "Senior Autonomous Data Engineer",
                        "company": "Uber Amsterdam Tech Center",
                        "location": "Amsterdam / Hybrid",
                        "salary": "€115,000 - €130,000",
                        "score": "90.6%",
                        "ref": "UBR-AMS-03",
                        "freshness": "DÜN GECE",
                        "analysis": "Gerçek zamanlı rota analitiği ve büyük veri akışlarında dağıtık mimari deneyimi.",
                        "skills": [
                              "Apache Spark",
                              "Flink",
                              "Python",
                              "GCP"
                        ],
                        "tier": "Senior Data Lead",
                        "source": "Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ams-4",
                        "title": "Staff SRE & Cloud Orchestration Lead",
                        "company": "Elastic European Headquarters",
                        "location": "Amsterdam / Remote",
                        "salary": "€125,000 - €145,000",
                        "score": "92.5%",
                        "ref": "EST-AMS-04",
                        "freshness": "BUGÜN TARANDI",
                        "analysis": "Küresel Elasticsearch bulut kümelerinde otonom hata giderme ve çok bölgeli Kubernetes yönetimi.",
                        "skills": [
                              "Kubernetes",
                              "Golang",
                              "Terraform",
                              "Distributed Cloud"
                        ],
                        "tier": "Staff SRE Lead",
                        "source": "Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ams-5",
                        "title": "Principal AI Search & Retrieval Engineer",
                        "company": "Miro Engineering Hub",
                        "location": "Amsterdam / Hybrid",
                        "salary": "€118,000 - €138,000",
                        "score": "91.1%",
                        "ref": "MRO-AMS-05",
                        "freshness": "DÜN GECE",
                        "analysis": "Görsel işbirliği tuvali için semantik arama, vektör indeksleme ve gerçek zamanlı veri eşitleme.",
                        "skills": [
                              "Vector DB",
                              "FastAPI",
                              "WebSockets",
                              "RAG Pipeline"
                        ],
                        "tier": "Principal Search Lead",
                        "source": "Workday ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "berlin": {
            "name": "BERLİN, ALMANYA",
            "lat": 52.52,
            "lng": 13.405,
            "count": 5,
            "dossiers": [
                  {
                        "id": "ber-1",
                        "title": "Staff Distributed Backend Engineer",
                        "company": "N26 European Hub",
                        "location": "Berlin / Remote",
                        "salary": "€115,000 - €135,000",
                        "score": "91.4%",
                        "ref": "BER-N26-01",
                        "freshness": "YENİ E-POSTA",
                        "analysis": "Fintech seviyesinde sıfır hata toleranslı asenkron işlem kuyrukları ve dayanıklı sistem tasarımı.",
                        "skills": [
                              "Java / Python",
                              "FastAPI",
                              "Distributed Systems",
                              "Kafka"
                        ],
                        "tier": "Staff Engineer",
                        "source": "Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ber-2",
                        "title": "Lead AI Automation & Microservices Architect",
                        "company": "Delivery Hero Core",
                        "location": "Berlin / Hybrid",
                        "salary": "€120,000 - €138,000",
                        "score": "93.2%",
                        "ref": "DLV-BER-02",
                        "freshness": "4 SAAT ÖNCE",
                        "analysis": "Otomatik sipariş eşleştirme ve akıllı rotalama algoritmalarında yüksek ölçekli mikroservis omurgası.",
                        "skills": [
                              "Go",
                              "Kubernetes",
                              "Redis Cluster",
                              "System Architecture"
                        ],
                        "tier": "Tech Lead",
                        "source": "Lever ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ber-3",
                        "title": "Senior Platform Reliability Engineer",
                        "company": "SoundCloud Tech Hub",
                        "location": "Berlin / Remote",
                        "salary": "€105,000 - €122,000",
                        "score": "89.9%",
                        "ref": "SND-BER-03",
                        "freshness": "DÜN 16:20",
                        "analysis": "Dağıtık medya akışları ve küresel CDN kenar sunucularında sıfır gecikmeli gözlemlenebilirlik.",
                        "skills": [
                              "Terraform",
                              "Kubernetes",
                              "Prometheus",
                              "Golang"
                        ],
                        "tier": "Senior SRE",
                        "source": "Greenhouse ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ber-4",
                        "title": "Principal Embedded AI & Edge Architect",
                        "company": "Tier Mobility Core",
                        "location": "Berlin / Hybrid",
                        "salary": "€110,000 - €128,000",
                        "score": "90.7%",
                        "ref": "TIR-BER-04",
                        "freshness": "5 SAAT ÖNCE",
                        "analysis": "Mikro-mobilite araç filolarında kenar bilişim ve telemetri işleme motorları.",
                        "skills": [
                              "C++",
                              "Edge AI",
                              "IoT Telemetry",
                              "MQTT"
                        ],
                        "tier": "Principal Edge Architect",
                        "source": "Lever ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ber-5",
                        "title": "Staff Rust Infrastructure Engineer",
                        "company": "Trade Republic Engineering",
                        "location": "Berlin / Remote",
                        "salary": "€118,000 - €136,000",
                        "score": "93.6%",
                        "ref": "TRP-BER-05",
                        "freshness": "BUGÜN 10:20",
                        "analysis": "Milyonlarca Avrupalı yatırımcı için sıfır gecikmeli hisse takas altyapısı ve Rust mikroservisleri.",
                        "skills": [
                              "Rust",
                              "Tokio",
                              "High-Throughput IO",
                              "Kafka"
                        ],
                        "tier": "Staff Engineer",
                        "source": "Trade Republic Careers",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "zurich": {
            "name": "ZÜRİH, İSVİÇRE",
            "lat": 47.3769,
            "lng": 8.5417,
            "count": 5,
            "dossiers": [
                  {
                        "id": "zur-1",
                        "title": "Senior Quantitative AI Engineer",
                        "company": "Swiss Wealth Intelligence Hub",
                        "location": "Zürich / Hybrid",
                        "salary": "CHF 190,000 - CHF 225,000",
                        "score": "93.1%",
                        "ref": "ZUR-SWI-01",
                        "freshness": "ÖZEL MANDATE",
                        "analysis": "İsviçre bankacılık ve fintech ekosistemi için yüksek güvenilirlikli veri boru hatları ve LLM ajanları geliştirme pozisyonu.",
                        "skills": [
                              "Python",
                              "FastAPI",
                              "Security / Encryption",
                              "Financial ML"
                        ],
                        "tier": "Senior Lead Specialist",
                        "source": "Swiss Private ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "zur-2",
                        "title": "Principal Security & Enclave Architect",
                        "company": "Swisscom Trust Lab",
                        "location": "Zürich / On-site",
                        "salary": "CHF 200,000 - CHF 240,000",
                        "score": "95.5%",
                        "ref": "SWC-ZUR-02",
                        "freshness": "BUGÜN 10:15",
                        "analysis": "Gizli hesaplama (Confidential Computing), donanımsal güvenli alanlar (Enclave) ve AES-256 veri koruma standartlarında liderlik rolü.",
                        "skills": [
                              "Confidential Computing",
                              "C++",
                              "Rust",
                              "Zero-Trust Architecture"
                        ],
                        "tier": "Principal Security Lead",
                        "source": "Swisscom Careers",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "zur-3",
                        "title": "Staff Distributed Cloud Systems Engineer",
                        "company": "Google Zurich Partner Hub",
                        "location": "Zürich / Hybrid",
                        "salary": "CHF 210,000 - CHF 255,000",
                        "score": "94.0%",
                        "ref": "GOO-ZUR-03",
                        "freshness": "DÜN GECE",
                        "analysis": "Dağıtık dosya sistemleri, küresel depolama katmanları ve asenkron replikasyon optimizasyonu.",
                        "skills": [
                              "C++ Core",
                              "Distributed Systems",
                              "Borg / K8s",
                              "Go"
                        ],
                        "tier": "Staff Engineer",
                        "source": "Direct Talent Portal",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "zur-4",
                        "title": "Lead Autonomous Robotics & Perception Lead",
                        "company": "ETH AI Center Spin-off",
                        "location": "Zürich / Hybrid",
                        "salary": "CHF 185,000 - CHF 220,000",
                        "score": "92.8%",
                        "ref": "ETH-ZUR-04",
                        "freshness": "YENİ TARANDI",
                        "analysis": "Endüstriyel dronlar ve otonom araçlar için 3D nokta bulutu işleme ve SLAM algoritmaları.",
                        "skills": [
                              "C++20",
                              "ROS2",
                              "SLAM",
                              "Point Cloud"
                        ],
                        "tier": "Lead Perception Architect",
                        "source": "Swiss Tech Hub",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "zur-5",
                        "title": "Principal Cryptographic Protocol Engineer",
                        "company": "Web3 Foundation Zurich",
                        "location": "Zug / Zürich / Remote",
                        "salary": "CHF 195,000 - CHF 230,000",
                        "score": "91.3%",
                        "ref": "W3F-ZUR-05",
                        "freshness": "DÜN GECE",
                        "analysis": "Sıfır bilgi ispatları (ZKP) ve dağıtık mutabakat protokollerinde çekirdek kriptografik mühendislik.",
                        "skills": [
                              "Rust",
                              "ZK-SNARKs",
                              "Consensus Algorithms",
                              "Applied Crypto"
                        ],
                        "tier": "Principal Cryptographer",
                        "source": "Web3 ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "dubai": {
            "name": "DUBAİ, BAE",
            "lat": 25.2048,
            "lng": 55.2708,
            "count": 5,
            "dossiers": [
                  {
                        "id": "dxb-1",
                        "title": "Principal Sovereign Cloud & AI Architect",
                        "company": "G42 Technology Hub",
                        "location": "Dubai & Abu Dhabi / On-site",
                        "salary": "$190,000 - $240,000 Vergisiz + Lüks Paket",
                        "score": "96.1%",
                        "ref": "G42-DXB-01",
                        "freshness": "ÖZEL LİDERLİK İLANI",
                        "analysis": "Bölgesel süper-bilgisayar kümeleri ve egemen yapay zekâ altyapısının ölçeklendirilmesi için baş mimar rolü.",
                        "skills": [
                              "AI Supercomputing",
                              "High-Scale Cloud",
                              "Python / C++",
                              "Inference"
                        ],
                        "tier": "Executive Architect",
                        "source": "G42 Executive Portal",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "dxb-2",
                        "title": "Staff Autonomous Systems Lead",
                        "company": "Careem Engineering Hub",
                        "location": "Dubai Internet City",
                        "salary": "$150,000 - $185,000 Vergisiz",
                        "score": "92.6%",
                        "ref": "CRM-DXB-02",
                        "freshness": "3 SAAT ÖNCE",
                        "analysis": "Süper-uygulama ekosisteminde dinamik fiyatlandırma ve otonom lojistik yönlendirme motorları.",
                        "skills": [
                              "Golang",
                              "Microservices",
                              "Kafka",
                              "Redis"
                        ],
                        "tier": "Staff Lead",
                        "source": "Workday ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "dxb-3",
                        "title": "Senior FinTech Security & Cryptography Lead",
                        "company": "DIFC Innovation Center",
                        "location": "DIFC, Dubai",
                        "salary": "$140,000 - $170,000 Vergisiz",
                        "score": "90.8%",
                        "ref": "DIF-DXB-03",
                        "freshness": "DÜN AKŞAM",
                        "analysis": "Dijital varlık takas altyapıları ve kurumsal ödeme ağları için şifreleme ve güvenlik mimarisi.",
                        "skills": [
                              "Applied Cryptography",
                              "Python",
                              "Secure Enclaves",
                              "API Security"
                        ],
                        "tier": "Senior Security Lead",
                        "source": "DIFC Talent Network",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "dxb-4",
                        "title": "Lead Multimodal Agent Systems Architect",
                        "company": "Technology Innovation Institute (TII)",
                        "location": "Abu Dhabi / Dubai Hub",
                        "salary": "$180,000 - $225,000 Vergisiz",
                        "score": "94.4%",
                        "ref": "TII-DXB-04",
                        "freshness": "3 SAAT ÖNCE",
                        "analysis": "Falcon açık model ailesi üzerinde otonom ajan koordinasyonu ve çok kipli çıkarım boru hatları.",
                        "skills": [
                              "PyTorch",
                              "vLLM",
                              "Distributed Training",
                              "Falcon Core"
                        ],
                        "tier": "Principal AI Scientist",
                        "source": "TII Talent Portal",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "dxb-5",
                        "title": "Principal Smart Cities & IoT Cloud Lead",
                        "company": "Dubai Future District",
                        "location": "DIFC, Dubai",
                        "salary": "$160,000 - $195,000 Vergisiz",
                        "score": "91.6%",
                        "ref": "DFD-DXB-05",
                        "freshness": "BUGÜN TARANDI",
                        "analysis": "Büyük kentsel altyapılarda milyonlarca sensör verisini gerçek zamanlı işleyen bulut mimarisi.",
                        "skills": [
                              "Kubernetes",
                              "Kafka",
                              "Python",
                              "Edge Computing"
                        ],
                        "tier": "Executive Architect",
                        "source": "Dubai Digital ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "tokyo": {
            "name": "TOKYO, JAPONYA",
            "lat": 35.6762,
            "lng": 139.6503,
            "count": 5,
            "dossiers": [
                  {
                        "id": "tyo-1",
                        "title": "Lead Autonomous Robotics & Vision Engineer",
                        "company": "Preferred Networks Ecosystem",
                        "location": "Tokyo / Hybrid (English Speaking)",
                        "salary": "¥16,000,000 - ¥20,000,000 Taban",
                        "score": "89.4%",
                        "ref": "TYO-PFN-01",
                        "freshness": "3 SAAT ÖNCE",
                        "analysis": "Endüstriyel otomasyon ve çok kipli multimodal modeller alanında küresel Ar-Ge liderliği.",
                        "skills": [
                              "PyTorch",
                              "C++",
                              "ROS2",
                              "Vision Transformers"
                        ],
                        "tier": "Principal Research Lead",
                        "source": "Tokyo AI Dispatch",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "tyo-2",
                        "title": "Staff Distributed Infrastructure Architect",
                        "company": "Mercari Tech Lab",
                        "location": "Roppongi, Tokyo / Remote",
                        "salary": "¥15,000,000 - ¥18,500,000",
                        "score": "91.8%",
                        "ref": "MRC-TYO-02",
                        "freshness": "BUGÜN TARANDI",
                        "analysis": "Japonya'nın en büyük mobil pazar yeri altyapısında mikroservis orkestrasyonu ve sıfır kesinti protokolü.",
                        "skills": [
                              "Go",
                              "Kubernetes",
                              "GCP Spanner",
                              "Terraform"
                        ],
                        "tier": "Staff Architect",
                        "source": "Mercari Careers ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "tyo-3",
                        "title": "Senior AI Compilers & CUDA Specialist",
                        "company": "Sony AI Innovation Hub",
                        "location": "Shinagawa, Tokyo",
                        "salary": "¥14,000,000 - ¥17,000,000",
                        "score": "90.2%",
                        "ref": "SNY-TYO-03",
                        "freshness": "DÜN GECE",
                        "analysis": "Donanım hızlandırmalı derin öğrenme çıkarımı ve özel çip optimizasyonunda çekirdek derleyici tasarımı.",
                        "skills": [
                              "CUDA",
                              "LLVM Compilers",
                              "C++20",
                              "TensorRT"
                        ],
                        "tier": "Senior Specialist",
                        "source": "Sony Global Talent",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "tyo-4",
                        "title": "Principal Natural Language Research Lead",
                        "company": "Rakuten Global AI",
                        "location": "Futako-Tamagawa, Tokyo",
                        "salary": "¥15,500,000 - ¥19,000,000",
                        "score": "92.1%",
                        "ref": "RKT-TYO-04",
                        "freshness": "4 SAAT ÖNCE",
                        "analysis": "Çok dilli büyük dil modelleri ve e-ticaret arama semantiği için derin öğrenme mimarileri.",
                        "skills": [
                              "Transformers",
                              "PyTorch",
                              "NLP",
                              "C++ Engine"
                        ],
                        "tier": "Principal Research Lead",
                        "source": "Rakuten Careers",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "tyo-5",
                        "title": "Staff Cloud Reliability & Edge Architect",
                        "company": "LINE Yahoo Engineering",
                        "location": "Kioicho, Tokyo / Remote",
                        "salary": "¥13,500,000 - ¥16,500,000",
                        "score": "90.6%",
                        "ref": "LYH-TYO-05",
                        "freshness": "DÜN AKŞAM",
                        "analysis": "200 milyondan fazla aktif kullanıcılı mesajlaşma altyapısında asenkron socket yönetimi.",
                        "skills": [
                              "Go",
                              "Kubernetes",
                              "Redis",
                              "Distributed Messaging"
                        ],
                        "tier": "Staff Reliability Lead",
                        "source": "LINE Careers ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "singapore": {
            "name": "SİNGAPUR",
            "lat": 1.3521,
            "lng": 103.8198,
            "count": 5,
            "dossiers": [
                  {
                        "id": "sin-1",
                        "title": "Staff Cloud Platform & Edge Infrastructure",
                        "company": "Grab FinTech Cloud",
                        "location": "Singapore / Hybrid",
                        "salary": "SGD 180,000 - SGD 220,000",
                        "score": "92.0%",
                        "ref": "SIN-GRB-01",
                        "freshness": "BUGÜN TARANDI",
                        "analysis": "Güneydoğu Asya çapında dağıtık mikroservis yönetimi ve yüksek hacimli finansal işlem altyapısı.",
                        "skills": [
                              "Kubernetes",
                              "Go",
                              "Terraform",
                              "Low-Latency Architecture"
                        ],
                        "tier": "Staff Infra Architect",
                        "source": "Workday ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sin-2",
                        "title": "Principal Machine Learning Operations Lead",
                        "company": "Sea Group Engineering",
                        "location": "Singapore / On-site",
                        "salary": "SGD 190,000 - SGD 235,000",
                        "score": "93.7%",
                        "ref": "SEA-SIN-02",
                        "freshness": "4 SAAT ÖNCE",
                        "analysis": "Milyarlarca tahmini yöneten ölçekte MLOps boru hatları, özellik depoları ve model dağıtım süreçleri.",
                        "skills": [
                              "Kubeflow",
                              "MLflow",
                              "Python",
                              "Distributed Systems"
                        ],
                        "tier": "Principal MLOps Lead",
                        "source": "Sea Group Portal",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sin-3",
                        "title": "Senior High-Throughput Trading Systems Engineer",
                        "company": "Singtel Future Lab",
                        "location": "Marina Bay, Singapore",
                        "salary": "SGD 160,000 - SGD 195,000",
                        "score": "89.5%",
                        "ref": "SNT-SIN-03",
                        "freshness": "DÜN AKŞAM",
                        "analysis": "Telekom seviyesinde kenar bilişim ve ultra düşük gecikmeli veri akışı yönetimi.",
                        "skills": [
                              "Rust / C++",
                              "Networking IO",
                              "Linux Kernel Tuning",
                              "Edge AI"
                        ],
                        "tier": "Senior Systems Engineer",
                        "source": "LinkedIn Talent Feed",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sin-4",
                        "title": "Staff AI Privacy & Secure Computation Lead",
                        "company": "A*STAR Computing Hub",
                        "location": "Singapore / On-site",
                        "salary": "SGD 170,000 - SGD 210,000",
                        "score": "92.3%",
                        "ref": "AST-SIN-04",
                        "freshness": "YENİ TARANDI",
                        "analysis": "Diferansiyel gizlilik (Differential Privacy) ve homomorfik şifreleme ile yapay zekâ model eğitimi.",
                        "skills": [
                              "Applied Crypto",
                              "Python",
                              "Secure Enclaves",
                              "C++"
                        ],
                        "tier": "Staff Scientist",
                        "source": "Singapore Govt ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "sin-5",
                        "title": "Principal Full-Stack FinTech Architect",
                        "company": "DBS Digital Bank Lab",
                        "location": "Marina Bay Financial Centre",
                        "salary": "SGD 175,000 - SGD 215,000",
                        "score": "91.0%",
                        "ref": "DBS-SIN-05",
                        "freshness": "DÜN GECE",
                        "analysis": "Yeni nesil mikro-önuç mimarileri ve yüksek erişilebilirlikli finansal API geçitleri.",
                        "skills": [
                              "Next.js",
                              "Java Spring Boot",
                              "Kafka",
                              "Cloud Architecture"
                        ],
                        "tier": "Principal Architect",
                        "source": "DBS Direct ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      },
      "istanbul": {
            "name": "İSTANBUL, TÜRKİYE (MERKEZ RADAR)",
            "lat": 41.0082,
            "lng": 28.9784,
            "count": 5,
            "dossiers": [
                  {
                        "id": "ist-1",
                        "title": "Lead AI & Autonomous Systems Specialist",
                        "company": "Yerli AI Araştırma Laboratuvarı",
                        "location": "İstanbul (Levent / Hibrit)",
                        "salary": "₺180,000 - ₺240,000 / Ay Net",
                        "score": "96.4%",
                        "ref": "IST-AI-01",
                        "freshness": "YENİ TARANDI",
                        "analysis": "Türkiye merkezli öncü yapay zekâ Ar-Ge merkezinde yerel ve küresel LLM mimarilerini entegre edecek baş mimar pozisyonu. Tam yetkinlik örtüşmesi.",
                        "skills": [
                              "FastAPI",
                              "Next.js",
                              "Vektör Veritabanları",
                              "Otonom Ajanlar"
                        ],
                        "tier": "Principal Tech Lead",
                        "source": "LinkedIn Özel Davet",
                        "telegram": "Merkez Komuta VIP İletildi"
                  },
                  {
                        "id": "ist-2",
                        "title": "Principal Full-Stack Tech Lead",
                        "company": "Trendyol Tech / International Hub",
                        "location": "İstanbul / Remote",
                        "salary": "₺160,000 - ₺200,000 / Ay Net",
                        "score": "91.8%",
                        "ref": "IST-TRN-02",
                        "freshness": "DÜN GECE",
                        "analysis": "Yüksek ölçekli asenkron sistemler ve mikroservis mimarisi tecrübeniz aranan kriterlerle örtüşüyor.",
                        "skills": [
                              "Go / Python",
                              "React / Next.js",
                              "Kafka",
                              "PostgreSQL"
                        ],
                        "tier": "Staff Architect",
                        "source": "Trendyol Kariyer ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ist-3",
                        "title": "Staff Cloud Infrastructure & DevOps Architect",
                        "company": "Hepsiburada Tech Hub",
                        "location": "İstanbul / Hibrit",
                        "salary": "₺150,000 - ₺190,000 / Ay Net",
                        "score": "93.5%",
                        "ref": "IST-HPB-03",
                        "freshness": "2 SAAT ÖNCE",
                        "analysis": "Milyonlarca günlük siparişi karşılayan çoklu veri merkezi kümeleme ve Kubernetes orkestrasyonu liderliği.",
                        "skills": [
                              "Kubernetes",
                              "Terraform",
                              "CI/CD Pipeline",
                              "High Availability"
                        ],
                        "tier": "Staff Infrastructure",
                        "source": "Hepsiburada Kariyer",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ist-4",
                        "title": "Senior Distributed Systems & Cache Lead",
                        "company": "Getir Global Platform",
                        "location": "İstanbul (Etiler / Hibrit)",
                        "salary": "₺145,000 - ₺180,000 / Ay Net",
                        "score": "92.2%",
                        "ref": "GTR-IST-04",
                        "freshness": "4 SAAT ÖNCE",
                        "analysis": "Yüksek eşzamanlı anlık teslimat platformunda mikro-saniyelik önbellek yönetimi ve Redis kümeleme.",
                        "skills": [
                              "Node.js / Go",
                              "Redis Cluster",
                              "Kubernetes",
                              "Microservices"
                        ],
                        "tier": "Senior Lead Specialist",
                        "source": "Getir Careers ATS",
                        "telegram": "VIP Bildirim Gönderildi"
                  },
                  {
                        "id": "ist-5",
                        "title": "Principal FinTech Security & Core Banking Lead",
                        "company": "Papara Engineering",
                        "location": "İstanbul (Üsküdar / Hibrit)",
                        "salary": "₺155,000 - ₺195,000 / Ay Net",
                        "score": "94.3%",
                        "ref": "PPR-IST-05",
                        "freshness": "BUGÜN 12:10",
                        "analysis": "TCMB regülasyonlarına tam uyumlu finansal işlem altyapısı, tokenizasyon ve HSM güvenlik modülleri.",
                        "skills": [
                              "Go / .NET Core",
                              "PostgreSQL",
                              "HSM Encryption",
                              "Event-Driven"
                        ],
                        "tier": "Principal Architect",
                        "source": "Papara Kariyer",
                        "telegram": "VIP Bildirim Gönderildi"
                  }
            ]
      }
};

export function getAllDossiersFromDatabase(db: Record<string, CityHub>): Dossier[] {
  const all: Dossier[] = [];
  Object.entries(db).forEach(([key, city]) => {
    city.dossiers.forEach((d) => {
      all.push({ ...d, cityKey: key, cityName: city.name });
    });
  });
  return all;
}

export const CITY_DATABASE = initialCityDatabase;

