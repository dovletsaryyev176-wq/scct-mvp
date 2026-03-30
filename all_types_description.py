class DeliveryTimes:
    URGENT = 'urgent'                  # Срочно
    DURING_DAY = 'during_day'          # В течении дня
    SPECIFIC_TIME = 'specific_time'    # В конкретное время

    CHOICES = [
        URGENT,
        DURING_DAY,
        SPECIFIC_TIME,
    ]

    LABELS = {
        URGENT: {'ru': 'Срочно', 'tm': 'Çalt'},
        DURING_DAY: {'ru': 'В течении дня', 'tm': 'Gün içinde'},
        SPECIFIC_TIME: {'ru': 'В конкретное время', 'tm': 'Belli bir wagtda'},
    }

class OrderStatuses:
    PENDING = 'pending'                # В ожидании
    IN_PROGRESS = 'in_progress'        # В пути
    DELIVERED = 'delivered'            # Доставлено
    CANCELLED = 'cancelled'            # Отменено
    IN_PLACE='in_place'                # На месте

    CHOICES = [
        PENDING,
        IN_PROGRESS,
        DELIVERED,
        CANCELLED,
        IN_PLACE,
    ]

    LABELS = {
        PENDING: {'ru': 'В ожидании', 'tm': 'Garaşylýar'},
        IN_PROGRESS: {'ru': 'В пути', 'tm': 'Ýolda'},
        DELIVERED: {'ru': 'Доставлено', 'tm': 'Eltildi'},
        CANCELLED: {'ru': 'Отменено', 'tm': 'Ýatyryldy'},
        IN_PLACE: {'ru': 'На месте', 'tm': 'Ýerinde'},
    }

class PaymentTypes:
    CASH = 'cash'                      # Наличные
    CARD = 'card'                      # Карта
    CASH_AND_CARD = 'cash_and_card'   # Наличные и карта
    CREDIT = 'credit'                  # Кредит
    FREE = 'free'                      # Бесплатно

    CHOICES = [
        CASH,
        CARD,
        CASH_AND_CARD,
        CREDIT,
        FREE,
    ]

    LABELS = {
        CASH: {'ru': 'Наличные', 'tm': 'Nagt'},
        CARD: {'ru': 'Карта', 'tm': 'Karta'},
        CASH_AND_CARD: {'ru': 'Наличные и карта', 'tm': 'Nagt we karta'},
        CREDIT: {'ru': 'Кредит', 'tm': 'Kredit'},
        FREE: {'ru': 'Бесплатно', 'tm': 'Mugt'},
    }

class ServiceTypes:
    INCOMING = 'incoming'      # Забираю от клиента
    OUTCOMING = 'outcoming'    # Выдача клиенту
    TRANSFORMATION = 'transformation'  # Списание у клиента 

    
    LABELS = {
        INCOMING: {'ru': 'Забираем от клиента', 'tm': 'Klientden almak'},
        OUTCOMING: {'ru': 'Выдаем клиенту', 'tm': 'Kliente bermek'},
        TRANSFORMATION: {'ru': 'Списываем у клиента', 'tm': 'Klientden hasapdan çykarmak'},
    }

class TransactionTypes:
    INVENTORY_IN = 'inventory_in'      # Приход с завода
    COURIER_ISSUE = 'courier_issue'    # Выдача курьеру (Утро)
    COURIER_RETURN = 'courier_return'  # Прием от курьера (Вечер)
    COURIER_TRANSFER = 'courier_transfer' # Между курьерами
    WRITE_OFF = 'write_off'            # Списание (утиль/брак)

    
    LABELS = {
        INVENTORY_IN: {'ru': 'Приход с контрагента', 'tm': 'Kontragentdan gelýän'},
        COURIER_ISSUE: {'ru': 'Выдача курьеру', 'tm': 'Kurýere bermek'},
        COURIER_RETURN: {'ru': 'Прием от курьера', 'tm': 'Kurýerden kabul etmek'},
        COURIER_TRANSFER: {'ru': 'Перевод между курьерами', 'tm': 'Başga kurýere geçirmek'},
        WRITE_OFF: {'ru': 'Списание', 'tm': 'Hasapdan çykarmak'},
    }

class DiscountTypes:
    FIXED_AMOUNT = 'fixed_amount'      # фиксированная цена
    PERCENTAGE = 'percentage'    # скидка в процентах
    FREE_N_TH_ORDER = 'free_n_th_order'  # номерной заказ бесплатно
    FIXED_PRICE = 'fixed_price' # скидка фиксированной суммой
    
    
    LABELS = {
        FIXED_AMOUNT: {'ru': 'Фиксированная цена', 'tm': 'Belli sana belli baha'},
        PERCENTAGE: {'ru': 'Скидка в процентах', 'tm': 'Göterimli'},
        FREE_N_TH_ORDER: {'ru': 'Номерной заказ бесплатно', 'tm': 'Sargydyň belgisine görä'},
        FIXED_PRICE: {'ru': 'Скидка фиксированной суммой', 'tm': 'Belli bir nyrh düşmesi'},
    }

